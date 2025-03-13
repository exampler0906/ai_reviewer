import httpx
import json
import os
import aiohttp
import common_function
from ai_code_reviewer_logger import logger
from httpx import AsyncClient


def read_json_file(file_path : str) -> dict | None: 
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        logger.info("JSON file loaded successfully:")
        return data
        
    except FileNotFoundError:
        logger.exception(f"Error: File {file_path} not found. Please check if the path is correct.")
        raise
    except json.JSONDecodeError as e:
        logger.exception(f"Error: Invalid JSON format, unable to parse!\nDetails: {e}, file path:{file_path}")
        raise
    except PermissionError:
        logger.exception(f"Error: No permission to read the file {file_path}. Please check file permissions.")
        raise
    except Exception as e:
        logger.exception(f"An unknown error occurred: {e}, file path:{file_path}")
        raise


class DeepSeek:
    
    # 默认提示词为lever_0
    DEFAULT_PROMPT = """你是一名经验丰富的计算机工程师，请从专业的角度，对以下代码进行review，对于不完善的地方，请提出针对性的优化建议。
                                  在给出意见时请保持语言的简洁，只需对可能导致程序严重错误的地方提出修改建议，无需给出示例代码。
                                  review 时不需要吹毛求疵，如果没有更好的优化建议，建议的内容可以为空"""
    
    def __init__(self, url:str, key:str):
        # 参数校验
        common_function.parameter_check(url, "url")
        common_function.parameter_check(key, "api key")
        
        common_function.log_init_check()
        
        # 安全赋值
        self.api_url = url.strip()
        # 私有变量保护敏感数据
        self._api_key = key.strip()
        
        # 这个超时时间给的比较长是因为LLM的应答速度可能较慢
        try: 
            self.client = AsyncClient(trust_env=False, proxy=None, timeout=1000)
        except Exception as e:
            logger.exception(f"Init async client error1")
            raise RecursionError("Init async client error") from e
        
        self.prompt = read_json_file("./promt_lever_configure.json")

        logger.info("Init ai model deepseek success")
        
        
    # 这个函数貌似没真正生效
    @property
    def api_key(self):
        # 对api key进行隐藏
        if len(self._api_key) > 10:
            return f"****{self._api_key[-4:]}" if self._api_key else None
        return None
    
    async def close(self):
        # 释放api key，防止其在内存中驻留
        self._api_key = None  # 主动清除敏感数据
        await self.client.aclose() # 主动释放链接
        self.client = None

    
    async def call_deepseek_async(self, prompt: str) -> any:
        # 步调用 DeepSeek API 并返回结果
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-r1-250120",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            with await self.client.post(
                self.api_url,
                json=payload,
                headers=headers) as response:
    
                response.raise_for_status()  # 自动触发HTTPError 
                response_json = response.json()     # FIXME:相应体较大未考虑   
                return response_json
        
        except httpx.HTTPStatusError as e:
            logger.exception(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.exception(f"Network error: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON response: {e.doc}")
            raise
        except Exception as e:
            logger.exception(f"Unknow Error: {e}")
            raise

    async def call_ai_model(self, code_content):
        logger.info("Start call ai model")
        
        #主函数，调用 DeepSeek 并输出结果
        prompt_lever = os.environ.get("PROMPT_LEVER")
        if not prompt_lever in self.prompt:
            full_prompt = f"{self.prompt[prompt_lever]}\n{code_content}"
        else:
            full_prompt = f"{self.DEFAULT_PROMPT}\n{code_content}"
        
        logger.debug(f"Request content:{full_prompt}")
        
        try:
            response = await self.call_deepseek_async(full_prompt)
            response.raise_for_status()
            logger.debug(f"DeepSeek Response:{response}")
        except HTTPError as e:
            logger.exception(f"Call ai model error:{str(e)}")
            raise
        except Exception as e:
            logger.exception(f"Unknow Error: {e}")
            raise
        
        if  isinstance(response, dict) and ("choices" in response and response["choices"]):
            response_str = response["choices"][0]["message"]["content"]
            return response_str
        else:
            return "AI model response error"
