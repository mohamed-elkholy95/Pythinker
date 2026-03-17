from typing import Any


class AppError(RuntimeError):
    def __init__(
        self,
        code: int,
        msg: str,
        status_code: int = 400,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status_code = status_code
        self.data = data
        self.headers = headers or {}


class NotFoundError(AppError):
    def __init__(self, msg: str = "Resource not found"):
        super().__init__(code=404, msg=msg, status_code=404)


class BadRequestError(AppError):
    def __init__(self, msg: str = "Bad request parameters"):
        super().__init__(code=400, msg=msg, status_code=400)


class ValidationError(AppError):
    def __init__(self, msg: str = "Validation error"):
        super().__init__(code=422, msg=msg, status_code=422)


class ServerError(AppError):
    def __init__(self, msg: str = "Internal server error"):
        super().__init__(code=500, msg=msg, status_code=500)


class UnauthorizedError(AppError):
    def __init__(
        self,
        msg: str = "Authentication required",
        *,
        error_code: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        data = {"code": error_code} if error_code else None
        super().__init__(code=401, msg=msg, status_code=401, data=data, headers=headers)
