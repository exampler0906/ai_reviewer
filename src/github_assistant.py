import requests
import os
import json
import re
from ai_code_reviewer_logger import logger
from dataclasses import dataclass
from enum import Enum

@dataclass
class DiffFileStruct:
    file_name: str
    file_path: str
    diff_position: list


class RequestMethode(Enum):
    GET = 1
    POST = 2


class GithubAssistant:
    def __init__(
        self,
        github_token: str,
        repository_owner: str,
        repository_name: str,
        pull_request_id: int
    ):
        # 参数类型校验
        if not isinstance(github_token, str) or not github_token.strip():
            raise ValueError("github_token must be a non-empty string")
        if not isinstance(repository_owner, str) or not repository_owner:
            raise ValueError("repository_owner must be a non-empty string")
        if not isinstance(repository_name, str) or not repository_name:
            raise ValueError("repository_name must be a non-empty string")
        if not isinstance(pull_request_id, int) or pull_request_id <= 0:
            raise ValueError("pull_request_id must be a positive integer")

        # 敏感数据设为私有属性
        self._github_token = github_token  
        self.owner = repository_owner
        self.repo = repository_name
        self.pull_request_id = pull_request_id
        
        # 设置github api 请求头
        self.headers = {
        "Authorization": f"token {self._github_token}",
        "Accept": "application/vnd.github.v3+json"
        }
        
        self.pr_base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}"
        
        # 获取 commit SHA
        response_json =  self.call_github_api(RequestMethode.GET, self.pr_base_url)
        if "head" not in response_json or "sha" not in response_json["head"]:
            raise KeyError("Missing commit SHA in PR data")
        self.commit_sha = response_json["head"]["sha"]
    
        logger.info("Init github assistant success")
    
    async def close(self):
        self._github_token = None  # 主动清除敏感数据    
    
    # 对token进行保护
    @property
    def github_token(self) -> str:
        return f"****{self._github_token[-4:]}" if self._github_token else ""


    def call_github_api(self, request_method:RequestMethode, url:str, payload:dict = {}) -> any:
        response = None
        try:
            # 分页是考虑到可能应答内容过多
            if request_method == RequestMethode.GET:
                response = requests.get(url, headers=self.headers, timeout=10, params={'per_page': 100})
            elif request_method == RequestMethode.POST:
                response = requests.post(url, headers=self.headers, timeout=10, params={'per_page': 100}, json=payload)
            
            response.raise_for_status()  # 自动触发HTTPError
            response_json = response.json()
            logger.debug(f"API success response:{response_json}")
            return response_json
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise
        except json.JSONDecodeError:
            logger.error("Failed to parse response JSON")
            raise
        finally:
            if response:
                response.close()  # 显式释放连接资源
    
     
    def get_pr_change_files(self):
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}/files"
        return self.call_github_api(RequestMethode.GET, url)

    
    # FIXME:这个函数需要进一步测试其准确性
    def get_comment_positions(self, patch):
        positions = []
        patch_lines = patch.split("\n")
        hunk_header_re = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@')
        current_new_line = None

        for line in patch_lines:
            if line.startswith('@@'):
                match = hunk_header_re.match(line)
                current_new_line = int(match.group(2)) if match else None
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

        comment_url = f"{self.pr_base_url}/comments"
        payload = {
            "body": comment_text,
            "commit_id": self.commit_sha,  # PR 的最新 commit SHA (需提前获取)
            "path": filename,
            "position": max(position, 1) # 行数至少为1
        }
        self.call_github_api(RequestMethode.POST, comment_url, payload)

    
    def get_diff_file_structs(self):
        
        logger.info("Start get pull request's change files")
        # 遍历所有文件并添加评论
        files = self.get_pr_change_files()
        diff_file_struct_list = []
        
        for file in files:
            filename = file["filename"]
            filepath = f"../../{self.repo}/{filename}"
            patch = file.get("patch", "")
            positions = self.get_comment_positions(patch)
            diff_file_struct_list.append(DiffFileStruct(filename, filepath, positions)) 

        return diff_file_struct_list