"""API response/error envelope and global exception handling.

Follows API_DESIGN_STANDARD.md and CODING_STANDARDS.md sections 12-13:

Success:
    {"success": true, "data": {...}, "timestamp": "..."}

Error:
    {"success": false, "errorCode": "...", "message": "...", "timestamp": "..."}

Never expose database errors, stack traces, or internal details to clients.
"""

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ServiceError(Exception):
    """Base application error carrying a stable error code."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(ServiceError):
    def __init__(self, message: str):
        super().__init__("NOT_FOUND", message, status_code=404)


class ConflictError(ServiceError):
    def __init__(self, message: str):
        super().__init__("CONFLICT", message, status_code=409)


class ValidationError_(ServiceError):
    def __init__(self, message: str):
        super().__init__("VALIDATION_ERROR", message, status_code=422)


class UnauthorizedError(ServiceError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__("UNAUTHORIZED", message, status_code=401)


class ForbiddenError(ServiceError):
    def __init__(self, message: str = "Access denied"):
        super().__init__("FORBIDDEN", message, status_code=403)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _error_payload(error_code: str, message: str) -> dict:
    return {"success": False, "errorCode": error_code, "message": message, "timestamp": _now()}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_payload(exc.error_code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(f"HTTP_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload("VALIDATION_ERROR", "Request validation failed"),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_error_payload("INTERNAL_ERROR", "An unexpected error occurred. Please try again later."),
        )


def success_response(data: object = None) -> dict:
    return {"success": True, "data": data, "timestamp": _now()}
