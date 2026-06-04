from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import (
    create_access_token,
    generate_verification_token,
    hash_password,
    verify_email_token,
    verify_password,
)
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..email_service import (
    send_admin_registration_notification,
    send_verification_email,
)
from ..logger import get_logger
from ..models import User
from ..templating import templates


def _redir(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url=f"{settings.root_path}{path}", status_code=status_code)


router = APIRouter()
log = get_logger("auth")

MIN_PASSWORD_LENGTH = 8


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user=Depends(get_current_user)):
    if user:
        return _redir("/dashboard")
    return templates.TemplateResponse(
        "register.html", {"request": request, "user": None}
    )


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()

    if len(password) < MIN_PASSWORD_LENGTH:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "error": "Password must be at least 8 characters long.",
            },
        )

    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "error": "An account with this email address already exists.",
            },
        )

    token = generate_verification_token(email)
    new_user = User(
        email=email, password_hash=hash_password(password), verification_token=token
    )
    db.add(new_user)
    db.commit()

    try:
        await send_verification_email(email, token)
    except Exception as exc:
        log.error("Failed to send verification email to %s: %s", email, exc)
        db.delete(new_user)
        db.commit()
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "error": "Could not send confirmation email. Please try again later.",
            },
        )

    try:
        await send_admin_registration_notification(email)
    except Exception as exc:
        log.error("Failed to send admin registration notification: %s", exc)

    return _redir("/login?msg=registered")


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    email = verify_email_token(token)
    if not email:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "This confirmation link is invalid or has expired.",
            },
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": None, "error": "Account not found."},
        )

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return _redir("/login?msg=verified")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, msg: str = "", user=Depends(get_current_user)):
    if user:
        return _redir("/dashboard")

    success = ""
    if msg == "registered":
        success = (
            "Account created! Please check your inbox and confirm your email address."
        )
    elif msg == "verified":
        success = "Email confirmed. You can now sign in."

    return templates.TemplateResponse(
        "login.html", {"request": request, "user": None, "success": success}
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "Invalid email address or password.",
            },
        )

    if not user.is_verified:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "Please confirm your email address before signing in.",
            },
        )

    response = _redir("/dashboard")
    response.set_cookie(
        "access_token",
        create_access_token(user.id),
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        max_age=604800,  # 7 days
    )
    return response


@router.post("/logout")
async def logout():
    response = _redir("/login")
    response.delete_cookie("access_token")
    return response
