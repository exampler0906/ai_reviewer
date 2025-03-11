import httpx
from ai_code_reviewer_logger import logger

class DeepSeek:
    def __init__(self, url, key):
        self.api_url  = url
        self.api_key = key


    async def call_deepseek_async(self, prompt: str):
        """ 异步调用 DeepSeek API 并返回结果 """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-r1-250120",  # 选择模型
            "messages": [{"role": "user", "content": prompt}]
        }

        async with httpx.AsyncClient(trust_env=False, proxy=None, timeout=1000) as client:
            response = await client.post(self.api_url, json=payload, headers=headers)
            response_json = response.json()
        return response_json


    async def call_ai_module(self, code_content):
        #主函数，调用 DeepSeek 并输出结果
        code_content =  """你是一名经验丰富的计算机工程师，请从专业的角度，对以下代码进行review，对于不完善的地方，请提出针对性的优化建议。
                            在给出意见时请保持语言的简洁，并对内存泄漏、性能优化、错误处理三个方面进行重点检查。
                            另外，提交给你的函数都是一个独立的个体，无需进行关联推导。
                            最后，根据你的修改建议给出一个完整的示例代码\n""" + code_content
        
        logger.debug(f"Request content:{code_content}")
        response = await self.call_deepseek_async(code_content)

        if "choices" in response and response["choices"]:
            response_str = response["choices"][0]["message"]["content"]
            logger.debug(f"DeepSeek Response:{response_str}")
            return response_str
        else:
            logger.debug(f"Error in DeepSeek API Response:{response}")
            return response
