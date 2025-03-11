from tree_sitter import Language, Parser
from ai_code_reviewer_logger import logger
from ai_module import DeepSeek
from github_assistant import GithubAssistant
from exception import LogError, EnvironmentVariableError, AiCodeReviewerException
import tree_sitter_cpp
import tree_sitter_python
import json
import argparse
import os
import asyncio


# 获取代码内容
def read_file(file_path, mode="read"):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            if mode == "read":
                return file.read()
            elif mode == "lines":
                return (line for line in file)  # 生成器减少内存占用
    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {file_path}")
    except PermissionError:
        raise PermissionError(f"无权限访问文件: {file_path}")
    except UnicodeDecodeError as e:
        raise ValueError(f"文件编码错误: {e}") from e


class CppCodeAnalyzer:
    def __init__(self, pull_request_id):
        # 校验日志模块是否正常启动
        if logger == None:
            raise LogError(2)

        # 配置文件检查   
        def environment_variable_check(variable):
            if variable is str:
                value = os.environ.get(variable)
                if value is None:
                    raise EnvironmentVariableError(f"环境变量{variable}未设置", 3)
                return value
            else:
                error_type = type(variable)
                raise AiCodeReviewerException(f"变量类型错误:{error_type}", 4)
        
        # llm_api_key 和 github_token 需要从环境变量中拿取
        llm_api_key = environment_variable_check("LLM_API_KEY")
        llm_api_url = environment_variable_check("LLM_API_URL")
        github_token = environment_variable_check("GITHUB_TOKEN")
        repository_name = environment_variable_check("REPOSITORY_NAME")
        repository_owner = environment_variable_check("REPOSITORY_OWNER")
        
        # 初始化ai模型(目前只支持deepseek)
        self.ai_module = DeepSeek(llm_api_url, llm_api_key)
        
        # 初始化github assistant
        self.github_assistant = GithubAssistant(github_token, 
                                                repository_owner, 
                                                repository_name, pull_request_id)

        self._cpp_parser = None
        self._py_parser = None
        self.code_lines = []

    
    @property
    def cpp_parser(self) -> Parser:
        if not self._cpp_parser:
            self._cpp_parser = Parser(Language(tree_sitter_cpp.language()))
        return self._cpp_parser

    
    @property
    def py_parser(self) -> Parser:
        if not self._py_parser:
            self._py_parser = Parser(Language(tree_sitter_python.language()))
        return self._py_parser
        
    
    


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
                cpp_code = read_file(diff_file_struct.file_name)
                tree = self.cpp_parser.parse(bytes(cpp_code, "utf8"))
                # 获取根节点
                root_node = tree.root_node
                # 开始遍历 AST
                await self.find_functions(root_node, diff_file_struct.diff_position, diff_file_struct.file_name)
            elif file_name.endswith(".py"):
                py_code = read_file(diff_file_struct.file_name)
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