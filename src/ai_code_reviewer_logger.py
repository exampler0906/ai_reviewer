# logger.py
import sys
import logging
import structlog

# 配置文件日志 Handler（记录 DEBUG 及以上）
file_handler = logging.FileHandler("app.log", mode="w")
file_handler.setLevel(logging.DEBUG)  # 记录所有日志
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
))

# 配置终端日志 Handler（记录 INFO 及以上）
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)  # 只记录 INFO 及以上
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
))

# 配置 logging 适配 structlog
logging.basicConfig(
    level=logging.DEBUG,  # 全局最低日志级别
    handlers=[file_handler, console_handler],  # 添加两个 Handler
)

# 让 structlog 适配 logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            [structlog.processors.CallsiteParameter.FILENAME,
             structlog.processors.CallsiteParameter.LINENO]
        ),
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# 创建全局 logger ---
logger = structlog.get_logger("global_logger")