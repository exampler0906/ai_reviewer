import tree_sitter_cpp
import tree_sitter_python
import tree_sitter_java
import argparse
import os
import asyncio
import bisect
import aiofiles
import re
import common_function
import threading
from tree_sitter import Language, Parser
from ai_code_reviewer_logger import logger
from ai_module import DeepSeek
from github_assistant import GithubAssistant
from typing import Optional

class CppCodeAnalyzer:
    
    require_env_vars = (
        "LLM_API_KEY",
        "LLM_API_URL",
        "GITHUB_TOKEN",
        "REPOSITORY_NAME",
        "REPOSITORY_OWNER",
        "PROMPT_LEVEL"
    )
    
    # 待匹配的++文件的文件拓展名
    cpp_extensions = re.compile(r".*\.(cpp|hpp|h|tpp|cxx)$")
    python_extensions = re.compile(r".*\.py$")
    java_extensions = re.compile(r".*\.java$")
    
    lock = threading.Lock()
    
    semaphore = asyncio.Semaphore(os.cpu_count())
    
    def __init__(self, pull_request_id: int):
        
        # 批量校验环境变量
        missing_vars = [var for var in self.require_env_vars 
                       if not os.environ.get(var)]
        if missing_vars:
            raise RuntimeError(f":Missing environment variables: {', '.join(missing_vars)}")
        
        common_function.log_init_check()
        
        # llm_api_key 和 github_token 需要从环境变量中拿取
        llm_api_key = os.environ.get("LLM_API_KEY")
        llm_api_url = os.environ.get("LLM_API_URL")
        github_token = os.environ.get("GITHUB_TOKEN")
        repository_name = os.environ.get("REPOSITORY_NAME")
        repository_owner = os.environ.get("REPOSITORY_OWNER")
        
        try:
            # 初始化ai模型(目前只支持deepseek)
            self.ai_module = DeepSeek(llm_api_url, llm_api_key)
            
            # 初始化github assistant
            self.github_assistant = GithubAssistant(github_token, 
                                                    repository_owner, 
                                                    repository_name, pull_request_id)
        except Exception as e:
            logger.exception(f"Init ai_code_reviewer failed: {e}")
            raise
        
        # c++ 解析器
        self._cpp_parser = None
        # python 解析器
        self._py_parser = None
        # java 解析器
        self._java_parser = None
        logger.info("Init ai_code_reviewer success")

    
    @property
    def cpp_parser(self) -> Parser:
        try:
            with self.lock: # 多线程安全
                if self._cpp_parser is None:
                    self._cpp_parser = Parser(Language(tree_sitter_cpp.language()))
        except Exception as e:
            raise RuntimeError(f"Failed to initialize C++ parser:{e}") from e
        return self._cpp_parser
    
    @property
    def py_parser(self) -> Parser:
        try:
            with self.lock:
                if self._py_parser is None:
                    self._py_parser = Parser(Language(tree_sitter_python.language()))
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Python parser:{e}") from e
        return self._py_parser

    
    @property
    def java_parser(self) -> Parser:
        try:
            with self.lock:
                if self._java_parser is None:
                    self._java_parser = Parser(Language(tree_sitter_java.language()))
        except Exception as e:
            raise RuntimeError(f"Failed to initialize JAVA parser:{e}") from e
        return self._java_parser
    
    
    async def close(self):
        # 实现资源释放逻辑
        await asyncio.gather(self.ai_module.close(), self.github_assistant.close())
    
    
    async def analyze_functions(self, node, lines, file_name):
        new_lines = lines
        
        # 检查当前节点是否为函数定义
        if node.type == "function_definition":
            # 获取函数的开始和结束行
            func_start_line = node.start_point[0] + 1  # start_point 是 (行, 列)，索引从 0 开始
            func_end_line = node.end_point[0] + 1

            # 使用二分查找快速定位范围
            left = bisect.bisect_left(new_lines, func_start_line)
            right = bisect.bisect_right(new_lines, func_end_line)
            lines_to_process = new_lines[left:right]
            
            if lines_to_process:
                try:
                    # 业务处理
                    function_body = self.extract_function_body(node)
                    response = await self.ai_module.call_ai_model(function_body)
                    # 将 comments 添加到该函数变更的第一行 
                    self.github_assistant.add_comment(file_name, next(iter(lines_to_process), None), response)
                except Exception as e:
                    logger.exception(f"AI processing failed:{e}")
                    raise

            # 批量移除已处理行（维护有序性）
            new_lines= lines[:left] + lines[right:]
                
        # 递归地遍历子节点
        for child in node.children:
            await self.analyze_functions(child, new_lines, file_name)
    

    # FIXME: 提取逻辑可能需要优化
    def extract_function_body(self, node):
        function_body = []        
        # 递归遍历子节点，提取函数体的语法内容
        for child in node.children:
            text = getattr(child, "text", None)
            if text is None:
                continue  # 跳过无text属性的子节点
            try:
                # 统一处理字节类型或字符串类型
                decoded = text.decode("utf-8", errors="replace") if isinstance(text, bytes) else str(text)
                function_body.append(decoded)
            except Exception as e:
                # FIXME: 简单的跳过解码失败的项可能导致函数提取不完整
                continue  # 跳过解码失败的项
        
        return "\n".join(function_body)


    
    async def analyze(self, diff_file_struct):
        async with self.semaphore:
            try:
                # 进行文件过滤
                file_name = diff_file_struct.file_name
                if self.cpp_extensions.match(file_name):
                    parser = self.cpp_parser
                elif self.python_extensions.match(file_name):
                    parser = self.py_parser
                elif self.java_extensions.match(file_name):
                    parser = self.java_parser
                else:
                    return
                
                # 统一处理逻辑
                try:
                    logger.info(f"Start review file:{file_name}")
                    
                    # 异步读取文件
                    async with aiofiles.open(diff_file_struct.file_path, 'r') as f:
                        code = await f.read()
                    
                    # 语法树解析
                    tree = parser.parse(bytes(code, 'utf-8'))
                    root_node = tree.root_node
                    
                    # AST遍历
                    lines = diff_file_struct.diff_position
                    lines.sort()
                    await self.analyze_functions(
                        root_node, 
                        lines,
                        file_name
                    )
                    
                except IOError as e:
                    logger.exception(f"File read error:{file_name}, error: {e}")
                except ValueError as e:
                    logger.exception(f"Parsing error{file_name}, error: {e}")                    
            except Exception as e:
                logger.exception(f"Unknown error: error: {file_name}, error: {e}")
    
    
    async def analyze_code(self, diff_file_struct_list):
        await asyncio.gather(*[self.analyze(f) for f in diff_file_struct_list], return_exceptions=True)

        
async def async_main(pull_request_id: int):
    analyzer = CppCodeAnalyzer(pull_request_id)
    try:
        diff_files =  analyzer.github_assistant.get_diff_file_structs()
        if not diff_files:
            logger.warning(f"No files available for review")
            return
        await analyzer.analyze_code(diff_files)
    except Exception as e:
        logger.exception(f"Unknown error:{e}")
        raise
    finally:
        await analyzer.close()
        

def validate_args(args) -> int:
    
    if hasattr(args, 'pull_request_id'):
        if args.pull_request_id <= 0:
            raise ValueError("Pull request id must be greater than 0")
        return args.pull_request_id
    else:
        raise Exception("Error: Missing pull_request_id parameter")

        
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pull_request_id", type=int, help="pull request id")
    
    try:
        args = parser.parse_args()
        if (pr_id := validate_args(args)) is None:
            return
            
        logger.info(f"Start review pull request {pr_id}'s code")
        asyncio.run(async_main(pr_id), debug=True)
        
    except (ValueError, argparse.ArgumentError) as e:
        logger.exception(f"parameter error:{e}")
        raise
    except Exception as e:
        logger.exception(f"processing error:{e}")
        raise

if __name__ == "__main__":
    main()