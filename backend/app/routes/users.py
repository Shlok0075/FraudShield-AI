"""
FraudShield AI - Admin-only user management (PART 12, Week 12 Day 6).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.security import hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserOut, UserRegister, UserRoleUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserRegister, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_role(["admin"]))):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail={"error": {"code": "EMAIL_EXISTS", "message": "Email already registered"}})
    user = User(email=payload.email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, current_user.id, "user.create", "user", user.id, request.client.host if request.client else None,
               detail=f"created {payload.email} with role={payload.role}")
    return user


@router.patch("/{user_id}/role", response_model=UserOut)
def update_role(user_id: int, payload: UserRoleUpdate, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_role(["admin"]))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "User not found"}})
    previous = user.role
    user.role = payload.role
    db.commit()
    db.refresh(user)
    log_action(db, current_user.id, "user.update_role", "user", user.id, request.client.host if request.client else None,
               detail=f"{user.email}: {previous} -> {payload.role}")
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_role(["admin"]))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "User not found"}})
    email = user.email
    db.delete(user)
    db.commit()
    log_action(db, current_user.id, "user.delete", "user", user_id, request.client.host if request.client else None,
               detail=f"deleted {email}")
    return None
