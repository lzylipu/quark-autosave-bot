class QASException(Exception):
    """QAS API 业务错误"""
    def __init__(self, message: str):
        super().__init__(f"QAS: {message}")
