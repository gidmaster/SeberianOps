from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from app.config import settings

SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 3600

signer = TimestampSigner(settings.secret_key)

def create_session() -> str:
    return signer.sign("admin").decode()

def verify_session(token: str) -> bool:
    try:
        signer.unsign(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False

def get_session(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)

async def require_admin(request: Request):
    token = get_session(request)
    if not token or not verify_session(token):
        return RedirectResponse(url="/admin/login", status_code=303)
