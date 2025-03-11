from tree_sitter import Language, Parser
from ai_code_reviewer_logger import logger
from ai_module import DeepSeek
from github_assistant import GithubAssistant
import tree_sitter_cpp
import tree_sitter_python
import json
import argparse
import os
import asyncio


class CppCodeAnalyzer:
    def __init__(self, pull_request_id):
        #加载配置文件
        try:
            with open("../configure.json", "r", encoding="utf-8") as file:
                configure = json.load(file)
        except Exception as e:
            logger.error(f"严重错误:{e}")
            exit(-1)

        # llm_api_key 和 github_token 需要从环境变量中拿取
        llm_api_key = os.environ.get("LLM_API_KEY")
        github_token = os.environ.get("GITHUB_TOKEN")
        if llm_api_key == None or github_token == None:
            logger.error("环境变量LLM_API_KEY或者GITHUB_TOKEN未设置")
            exit(-1)
        
        # 配置文件检查
        self.configure_check(configure, "llm_api_url")
        self.configure_check(configure, "repository_owner")
        self.configure_check(configure, "repository_name")
        
        
        # 初始化ai模型(目前只支持deepseek)
        self.ai_module = DeepSeek(configure["llm_api_url"], llm_api_key)
        
        
        # 初始化github assistant
        self.github_assistant = GithubAssistant(github_token, 
                                                configure["repository_owner"], 
                                                configure["repository_name"], pull_request_id)

        self.cpp_parser = Parser(Language(tree_sitter_cpp.language()))
        self.py_parserc = Parser(Language(tree_sitter_python.language()))
        self.code_lines = []
        
    # 配置文件检查   
    def configure_check(self, json, key):
        if not key in json:
            logger.error(f"配置文件缺少关键字:{key}")
            exit(-1)
    
    # 获取代码内容
    def read_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content


    async def find_functions(self, node, lines, file_name):
        # 获取文件变更列表行数，方便后续滤重
        self.code_lines = lines
        self.code_lines.sort()

        # 检查当前节点是否为函数定义
        if node.type == "function_definition":
            # 获取函数的开始和结束行
            func_start_line = node.start_point[0] + 1  # start_point 是 (行, 列)，索引从 0 开始
            func_end_line = node.end_point[0] + 1

            # 如果函数的某些行号在我们关心的 `lines` 列表中
            is_processed = False
            for line in self.code_lines:
                if func_start_line <= line <= func_end_line:
                    if is_processed:
                        # 移除已经处理后的代码行，提高性能
                        self.code_lines.remove(line)
                        continue
                    
                    # 将当前函数的处理flag标记为true
                    is_processed = True

                    # 获取函数体并打印
                    function_body = self.extract_function_body(node)
                    response = await self.ai_module.call_ai_module(function_body)

                    # 添加修改意见到评论
                    self.github_assistant.add_comment(file_name, func_start_line, response)

                    # 移除已经处理后的代码行，提高性能
                    self.code_lines.remove(line)
                
        # 递归地遍历子节点
        for child in node.children:
            await self.find_functions(child, lines, file_name)
    

    # FIXME: 提取逻辑需要进一步优化
    def extract_function_body(self, node):
        """ 提取函数体的代码内容 """
        function_body = []        
        # 递归遍历子节点，提取函数体的语法内容
        for child in node.children:
            function_body.append(child.text.decode("utf-8"))
        
        return "\n".join(function_body)


    async def analyze_code(self, diff_file_struct_list):
        for diff_file_struct in diff_file_struct_list:

            # 进行文件过滤
            file_name = diff_file_struct.file_name
            if file_name.endswith(".cpp") or file_name.endswith(".h") or file_name.endswith(".hpp") or file_name.endswith(".tpp"):
                # 解析 C++ 代码
                cpp_code = self.read_file(diff_file_struct.file_name)
                tree = self.cpp_parser.parse(bytes(cpp_code, "utf8"))
                # 获取根节点
                root_node = tree.root_node
                # 开始遍历 AST
                await self.find_functions(root_node, diff_file_struct.diff_position, diff_file_struct.file_name)
            elif file_name.endswith(".py"):
                py_code = self.read_file(diff_file_struct.file_name)
                tree = self.py_parser.parse(bytes(py_code, "utf8"))         
                # 获取根节点
                root_node = tree.root_node
                # 开始遍历 AST
                await self.find_functions(root_node, diff_file_struct.diff_position, diff_file_struct.file_name)


def main():
    # 命令行参数将解析
    parser = argparse.ArgumentParser(description="使用帮助")
    parser.add_argument("pull_request_id", type=int, help="合并请求id（必填）")
    args = parser.parse_args()
    
    code_analyzer = CppCodeAnalyzer(args.pull_request_id)
    diff_file_struct_list = code_analyzer.github_assistant.get_diff_file_structs()
    asyncio.run(code_analyzer.analyze_code(diff_file_struct_list))


if __name__ == "__main__":
    main()