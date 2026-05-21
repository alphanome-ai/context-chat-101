class ChatContextError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
