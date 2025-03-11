class AiCodeReviewerException(Exception):
    
    # 自定义异常基类
    def __init__(self, message, error_code=1):
        self.message = message
        self.error_code = error_code
        super().__init__(message)

    def __str__(self):
        return f"[Error {self.error_code}]: {self.message}"
    

class LogInitError(AiCodeReviewerException):
    def __init__(self):
        super().__init__(f"日志模块初始化错误",2)
        

class EnvironmentVariableNotFound(AiCodeReviewerException):
    def __init__(self, message):
        super().__init__(message, 3)