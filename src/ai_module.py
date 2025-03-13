from ai_code_reviewer_logger import logger
from httpx import AsyncClient
import httpx
import json
import os
import aiohttp


def read_file(file_path : str) -> any: 
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        logger.info("JSON file loaded successfully:")
        return data
        
    except FileNotFoundError:
        logger.error(f"Error: File {file_path} not found. Please check if the path is correct.")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error: Invalid JSON format, unable to parse!\nDetails: {e}")
        raise
    except PermissionError:
        logger.error(f"Error: No permission to read the file {file_path}. Please check file permissions.")
        raise
    except Exception as e:
        logger.error(f"An unknown error occurred: {e}")
        raise 

class DeepSeek:
    def __init__(self, url:str, key:str):
        # 参数校验
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Invalid URL: non-empty string required")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Invalid API key: non-empty string required")
        
        # 安全赋值
        self.api_url = url.strip()
        # 私有变量保护敏感数据
        self._api_key = key.strip()
        
        # 这个超时时间给的比较长是因为LLM的应答速度可能较慢
        self.client = AsyncClient(trust_env=False, proxy=None, timeout=1000)
        
        self.prompt = read_file("./promt_lever_configure.json")

        # 默认提示词为lever_0
        self.DEFAULT_PROMPT = """你是一名经验丰富的计算机工程师，请从专业的角度，对以下代码进行review，对于不完善的地方，请提出针对性的优化建议。
                                  在给出意见时请保持语言的简洁，给出对应的修改建议即可，无需给出示例代码。
                                  在review时请对内存管理、性能优化、错误处理三个方面进行重点检查。"""

        logger.info("Init ai model deepseek success")
        
        
    # 这个函数貌似没真正生效
    @property
    def api_key(self):
        # 对api key进行隐藏
        return f"****{self._api_key[-4:]}" if self._api_key else ""
    
    async def close(self):
        # 释放api key，防止其在内存中驻留
        self._api_key = None  # 主动清除敏感数据
        await self.client.aclose() # 主动释放链接

    
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
            response = await self.client.post(
                self.api_url,
                json=payload,
                headers=headers
            )

            response.raise_for_status()  # 自动触发HTTPError 
            response_json = response.json()        
            return response_json
        
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e.doc}")



    async def call_ai_model(self, code_content):
        logger.info("Strat call ai model")
        
        #主函数，调用 DeepSeek 并输出结果
        prompt_lever = os.environ.get("PROMPT_LEVER")
        if not prompt_lever in self.prompt:
            full_prompt = f"{self.prompt[prompt_lever]}\n{code_content}"
        else:
            full_prompt = f"{self.DEFAULT_PROMPT}\n{code_content}"
        
        logger.debug(f"Request content:{full_prompt}")
        async with aiohttp.ClientSession() as session:
            try:
                response = await self.call_deepseek_async(full_prompt)
            except HTTPError as e:
                logger.error(f"Call ai model error:{str(e)}")
                raise
            finally:
                # 展示不处理状态码，保留原始response
                logger.debug(f"DeepSeek Response:{response}")
        
        if "choices" in response and response["choices"]:
            response_str = response["choices"][0]["message"]["content"]
            return response_str
        else:
            return "AI model response error"
