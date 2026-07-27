class TransLokaError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(TransLokaError):
    def __init__(self) -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message="The requested resource was not found.",
            status_code=404,
        )
