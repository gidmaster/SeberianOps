from fastapi import Request
from fastapi.responses import HTMLResponse
from app.templates import templates

from starlette.exceptions import HTTPException as StarletteHTTPException

async def http_exception_handler(request: Request, exc) -> HTMLResponse:
    code = exc.status_code
    title, message = ERROR_MESSAGES.get(code, ("Error", str(exc.detail)))
    return templates.TemplateResponse(
        request,
        "error.html",
        {"request": request, "code": code, "title": title, "message": message},
        status_code=code
    )

ERROR_MESSAGES = {
    404: ("Not Found", "This page doesn't exist or was moved."),
    500: ("Internal Server Error", "Something went wrong on our end."),
    403: ("Forbidden", "You don't have access to this resource."),
}

# async def http_exception_handler(request: Request, exc) -> HTMLResponse:
#     code = exc.status_code
#     title, message = ERROR_MESSAGES.get(code, ("Error", str(exc.detail)))
#     return templates.TemplateResponse(
#         "error.html",
#         {
#             "request": request,
#             "code": code,
#             "title": title,
#             "message": message,
#         },
#         status_code=code
#     )

async def server_error_handler(request: Request, exc: Exception) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "code": 500,
            "title": "Internal Server Error",
            "message": "Something went wrong on our end.",
        },
        status_code=500
    )
