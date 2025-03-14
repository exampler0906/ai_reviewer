from ai_code_reviewer_logger import logger

# 参数校验
def parameter_check(item : any, item_name : str):
    if not (isinstance(item, str) and item.strip()):
        raise ValueError(f"{item_name} must be a non-empty string")
    
# 校验日志模块是否正常启动
def log_init_check():
    if not hasattr(logger, 'info'):
        raise RuntimeError(f":log init error")