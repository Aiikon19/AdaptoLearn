class AppError(Exception):
    def __init__(self, message: str, status: int = 400, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field
