"""
FraudShield AI - Auth routes (PART 12.1-12.3, Week 7 Day 5)
================================================================
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.config.settings import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import Token, UserLogin, UserOut, UserRegister
from app.services.audit_service import log_action
from app.utils.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMAIL_EXISTS", "message": "Email already registered"}},
        )
    user = User(email=payload.email, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate, and record BOTH outcomes in the audit log.

    Failed attempts were previously not logged at all, which is exactly
    backwards: the successful logins are uninteresting, and repeated failures
    are what an investigator is looking for after a credential-stuffing
    attempt. The attempted email is recorded (never the password) so those
    attempts are attributable.
    """
    ip = request.client.host if request.client else None
    user = db.query(User).filter(User.email == payload.email).first()

    if user is None:
        log_action(db, None, "auth.login_failed", "user", None, ip,
                   detail=f"unknown email: {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"}},
        )

    if not verify_password(payload.password, user.password_hash):
        log_action(db, user.id, "auth.login_failed", "user", user.id, ip,
                   detail=f"wrong password for {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"}},
        )

    token = create_access_token(subject=str(user.id), role=user.role)
    log_action(db, user.id, "auth.login", "user", user.id, ip,
               detail=f"role={user.role}")
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
