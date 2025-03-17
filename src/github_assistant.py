import requests
import json
import re
import urllib.parse
import common_function
from ai_code_reviewer_logger import logger
from dataclasses import dataclass
from enum import Enum

@dataclass
class DiffFileStruct:
    file_name: str
    file_path: str
    diff_position: list


class GithubAssistant:
    
    hunk_header_re = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@')
    
    def __init__(
        self,
        github_token: str,
        repository_owner: str,
        repository_name: str,
        pull_request_id: int
    ):
        common_function.parameter_check(github_token, "github token")
        common_function.parameter_check(repository_owner, "repository owner")
        common_function.parameter_check(repository_name, "repository name")
        #common_function.parameter_check(pull_request_id, "pull request id")
        
        common_function.log_init_check()

        # 敏感数据设为私有属性
        self._github_token = github_token  
        self.owner = urllib.parse.quote(repository_owner, safe="") # 防止url注入
        self.repo = urllib.parse.quote(repository_name, safe="")
        self.pull_request_id = pull_request_id
        
        # 设置github api 请求头
        self.headers = {
        "Authorization": f"token {self._github_token}",
        "Accept": "application/vnd.github.v3+json"
        }
        
        self.pr_base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}"
        
        # 获取 commit SHA
        
        self._commit_sha = None
    
        logger.info("Init github assistant success")
    
    
    async def close(self):
        self._github_token = None  # 主动清除敏感数据    
    
    
    # 对token进行保护
    @property
    def github_token(self) -> str:
        if self._github_token is not None and len(self._github_token) > 10:
            return f"****{self._github_token[-4:]}" if self._github_token else None
        return None


    # 懒加载，需要时再获取
    @property
    def commit_sha(self) -> str | None:
        if self._commit_sha is None:
            response_json =  self.call_github_api("GET", self.pr_base_url)
            if "head" not in response_json or "sha" not in response_json["head"]:
                raise KeyError("Missing commit SHA in PR data")
            self._commit_sha = response_json["head"]["sha"]
        
        return self._commit_sha


    def call_github_api(self, request_method:str, url:str, payload:dict = None) -> any:
        try:
            with requests.request(request_method, url, headers=self.headers, timeout=10, json=payload) as response:
                response.raise_for_status()  # 自动触发HTTPError
                response_json = response.json()
                logger.debug(f"API success response:{response_json}")
                return response_json
        except requests.exceptions.RequestException as e:
            logger.exception(f"API request failed:{e}")
            raise
        except requests.exceptions.JSONDecodeError:
            logger.exception("Failed to parse response JSON")
        except Exception as e:
            logger.exception("Unknown error:{e}")
            raise
        
    
    # FIXME: 暂时不考虑分页
    def get_pr_change_files(self):
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}/files?per_page=100" # 目前最大支持单次100个文件的修改
        return self.call_github_api("GET", url)

    
    # FIXME:这个函数需要进一步测试其准确性
    def get_comment_positions(self, patch):
        positions = []
        patch_lines = patch.split("\n")
        
        current_new_line = None

        for line in patch_lines:
            if line.startswith('@@'):
                match = self.hunk_header_re.match(line)
                try:
                    current_new_line = int(match.group(2)) if match else logger.error("Hunk header analyze failed:{line}")
                except ValueError as e:
                    logger.exception("Value error:{e}")
                except Exception as e:
                    logger.exception("Unknown error:{e}")
                continue  # 跳过块头处理
            
            if current_new_line is None:
                continue  # 忽略无效块后的行

            if line.startswith("+"):
                if not line.startswith("+++"):  # 排除文件头
                    positions.append(current_new_line)
                current_new_line += 1  # 新增行影响后续行号
            elif line.startswith("-"):
                pass  # 删除行不影响新文件行号
            else:
                current_new_line += 1  # 上下文行递增行号

        return positions
    

    # 发送评论
    def add_comment(self, filename, position, comment_text):
        
        logger.info("Start call github api to add comment")
        logger.info(f"{self.commit_sha}")
        logger.info(f"{filename}")
        
        comment_url = f"{self.pr_base_url}/comments"
        payload = {
            "body": comment_text,
            "commit_id": self._commit_sha,  # PR 的最新 commit SHA (需提前获取)
            "path": filename,
            "position": max(position, 1) # 行数至少为1
        }
        self.call_github_api("POST", comment_url, payload)

    
    def get_diff_file_structs(self):
        
        logger.info("Start get pull request's change files")
        # 遍历所有文件并添加评论
        files = self.get_pr_change_files()
        diff_file_struct_list = []
        
        for file in files:
            if "filename" in file:
                filename = file.get("filename")
                filepath = f"../../{self.repo}/{filename}"
                patch = file.get("patch", "")
                positions = self.get_comment_positions(patch)
                diff_file_struct_list.append(DiffFileStruct(filename, filepath, positions)) 

        return diff_file_struct_list
