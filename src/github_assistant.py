import requests
import os
from ai_code_reviewer_logger import logger
from dataclasses import dataclass

@dataclass
class DiffFileStruct:
    file_name: str
    diff_position: list


class GithubAssistant:
    def __init__(self, github_token, repository_owner, repository_name, pull_request_id):
        self.github_token = github_token
        self.owner = repository_owner
        self.repo = repository_name
        self.pull_request_id = pull_request_id


    def get_pr_change_files(self):
        # 发送请求获取 PR 文件变更信息
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}/files"
        response = requests.get(url, headers=headers)
        logger.debug(f"Get File Change Response:{response.json()}")
        files = response.json()

        return files


    # 解析 patch 并找到需要评论的位置
    def get_comment_positions(self, patch):
        positions = []
        patch_lines = patch.split("\n")
        position = 0  # GitHub 的 diff 行索引

        for line in patch_lines:
            if not line.startswith('@@'):  # 跳过 diff 头部信息
                position += 1
            if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")):# 考虑新增的行和删除的行
                positions.append(position)
        return positions
    

    # 发送评论
    def add_comment(self, filename, position, comment_text):

        # 获取 PR 的 commit ID
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        pr_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}"
        pr_data = requests.get(pr_url, headers=headers).json()
        COMMIT_ID = pr_data["head"]["sha"]

        comment_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{self.pull_request_id}/comments"
        payload = {
            "body": comment_text,
            "commit_id": COMMIT_ID,  # PR 的最新 commit SHA (需提前获取)
            "path": filename,
            "position": position
        }
        response = requests.post(comment_url, headers=headers, json=payload)
        logger.debug(f"Add Comment Response:{response.json()}")
        return response.json()

    
    def get_diff_file_structs(self):
        # 遍历所有文件并添加评论
        files = self.get_pr_change_files()
        diff_file_struct_list = []
        repository_name = os.environ.get("REPOSITORY_NAME")
        
        for file in files:
            filename = file["filename"]
            filename = f"../../{repository_name}/{filename}"
            patch = file.get("patch", "")
            positions = self.get_comment_positions(patch)

            diff_file_struct_list.append(DiffFileStruct(filename, positions)) 

        return diff_file_struct_list