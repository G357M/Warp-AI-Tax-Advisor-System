"""
Authentication API routes.
"""
from datetime import timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from core.auth_tokens import (
    EMAIL_VERIFICATION,
    PASSWORD_RESET,
    consume_action_token,
    issue_action_token,
)
from core.database import get_db
from core.email_delivery import send_auth_email
from core.security import (
    create_access_token,
    hash_password,
    verify_password,
    get_current_user,
    SESSION_COOKIE_NAME,
)
from core.config import settings
from core.time_utils import utc_now
from models import User
from api.schemas import (
    ActionTokenRequest,
    AuthActionResponse,
    EmailActionRequest,
    PasswordResetRequest,
    RegistrationResponse,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


GENERIC_EMAIL_MESSAGE = "If the account is eligible, an email has been sent."
ACTION_COMPLETE_MESSAGE = "Account action completed."
EMAIL_UNAVAILABLE_MESSAGE = "Account email delivery is not configured."


def _registration_response(user: User, verification_required: bool) -> dict:
    payload = UserResponse.model_validate(user).model_dump()
    payload["verification_required"] = verification_required
    return payload


def _require_email_delivery() -> None:
    if not settings.EMAIL_DELIVERY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMAIL_UNAVAILABLE_MESSAGE,
        )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Register a new user."""
    
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    normalized_email = str(user_data.email).strip().lower()
    existing_email = db.query(User).filter(User.email == normalized_email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        username=user_data.username,
        email=normalized_email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        role="user",
        is_active=True,
        email_verified_at=None if settings.EMAIL_DELIVERY_ENABLED else utc_now(),
    )

    db.add(new_user)
    db.flush()
    raw_token = None
    if settings.EMAIL_DELIVERY_ENABLED:
        raw_token = issue_action_token(
            db,
            user=new_user,
            purpose=EMAIL_VERIFICATION,
            lifetime=timedelta(hours=settings.AUTH_EMAIL_VERIFICATION_HOURS),
            cooldown_seconds=settings.AUTH_EMAIL_RESEND_COOLDOWN_SECONDS,
        )
    db.commit()
    db.refresh(new_user)

    if raw_token:
        background_tasks.add_task(
            send_auth_email,
            EMAIL_VERIFICATION,
            new_user.email,
            raw_token,
        )
    return _registration_response(new_user, settings.EMAIL_DELIVERY_ENABLED)


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login and get access token."""
    
    # Find user
    user = db.query(User).filter(User.username == credentials.username).first()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    if settings.EMAIL_DELIVERY_ENABLED and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    
    # Update last login
    user.last_login = utc_now()
    db.commit()
    
    # Create access token
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "sv": getattr(user, "session_version", 0),
        }
    )
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        max_age=max_age,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": max_age,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    """Clear the browser session cookie; bearer API clients are unaffected."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.ENVIRONMENT == "production",
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.post("/resend-verification", response_model=AuthActionResponse)
def resend_verification(
    body: EmailActionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Issue a fresh verification email without disclosing account state."""
    _require_email_delivery()
    user = db.query(User).filter(User.email == str(body.email).lower()).first()
    if user and not user.email_verified:
        raw_token = issue_action_token(
            db,
            user=user,
            purpose=EMAIL_VERIFICATION,
            lifetime=timedelta(hours=settings.AUTH_EMAIL_VERIFICATION_HOURS),
            cooldown_seconds=settings.AUTH_EMAIL_RESEND_COOLDOWN_SECONDS,
        )
        if raw_token:
            db.commit()
            background_tasks.add_task(
                send_auth_email,
                EMAIL_VERIFICATION,
                user.email,
                raw_token,
            )
    return {"message": GENERIC_EMAIL_MESSAGE}


@router.post("/verify-email", response_model=AuthActionResponse)
def verify_email(body: ActionTokenRequest, db: Session = Depends(get_db)):
    user = consume_action_token(
        db,
        raw_token=body.token,
        purpose=EMAIL_VERIFICATION,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    user.email_verified_at = user.email_verified_at or utc_now()
    db.commit()
    return {"message": ACTION_COMPLETE_MESSAGE}


@router.post("/forgot-password", response_model=AuthActionResponse)
def forgot_password(
    body: EmailActionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Issue a reset email while keeping account existence private."""
    _require_email_delivery()
    user = db.query(User).filter(User.email == str(body.email).lower()).first()
    if user and user.is_active:
        raw_token = issue_action_token(
            db,
            user=user,
            purpose=PASSWORD_RESET,
            lifetime=timedelta(minutes=settings.AUTH_PASSWORD_RESET_MINUTES),
            cooldown_seconds=settings.AUTH_EMAIL_RESEND_COOLDOWN_SECONDS,
        )
        if raw_token:
            db.commit()
            background_tasks.add_task(
                send_auth_email,
                PASSWORD_RESET,
                user.email,
                raw_token,
            )
    return {"message": GENERIC_EMAIL_MESSAGE}


@router.post("/reset-password", response_model=AuthActionResponse)
def reset_password(body: PasswordResetRequest, db: Session = Depends(get_db)):
    user = consume_action_token(
        db,
        raw_token=body.token,
        purpose=PASSWORD_RESET,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    user.password_hash = hash_password(body.new_password)
    user.session_version += 1
    db.commit()
    return {"message": ACTION_COMPLETE_MESSAGE}
