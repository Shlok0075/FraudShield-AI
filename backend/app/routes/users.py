"""
FraudShield AI - Admin-only user management (PART 12, Week 12 Day 6).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.security import hash_password
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import CaseNote, FraudCase
from app.models.feedback import FraudFeedback
from app.models.fraud_alert import FraudAlert
from app.models.user import User
from app.schemas.auth import AdminUserCreate, UserOut, UserRoleUpdate
from app.services.audit_service import log_action
from app.services.investigation_service import SYSTEM_EMAIL

router = APIRouter(prefix="/users", tags=["users"])


def _refuse(code: str, message: str, status: int = 400):
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def _is_last_admin(db: Session, user: User) -> bool:
    return user.role == "admin" and db.query(User).filter(User.role == "admin", User.id != user.id).count() == 0


def _has_history(db: Session, user_id: int) -> bool:
    """True when other rows point at this user (audit trail, cases, notes, alerts, feedback).
    Deleting such an account fails on Postgres (foreign keys) and would orphan the audit trail."""
    return any(db.query(model.id).filter(col == user_id).first() is not None for model, col in (
        (AuditLog, AuditLog.user_id), (FraudCase, FraudCase.assigned_to), (CaseNote, CaseNote.author_id),
        (FraudAlert, FraudAlert.resolved_by), (FraudFeedback, FraudFeedback.reviewer_id)))


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    # The automation account (system@...) can never log in and is not an account an admin manages.
    return db.query(User).filter(User.email != SYSTEM_EMAIL).order_by(User.created_at.desc(), User.id.desc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: AdminUserCreate, request: Request, db: Session = Depends(get_db),
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
    if user.email == SYSTEM_EMAIL:
        _refuse("SYSTEM_ACCOUNT", "The automation account cannot be changed.")
    if payload.role != "admin" and _is_last_admin(db, user):
        _refuse("LAST_ADMIN", "This is the only admin. Make another user an admin first.")
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
    if user.id == current_user.id:
        _refuse("SELF_DELETE", "You cannot delete your own account.")
    if user.email == SYSTEM_EMAIL:
        _refuse("SYSTEM_ACCOUNT", "The automation account cannot be deleted.")
    if _is_last_admin(db, user):
        _refuse("LAST_ADMIN", "This is the only admin, so it cannot be deleted.")
    if _has_history(db, user.id):
        _refuse("HAS_HISTORY", "This account has activity in the audit log and cases, which must be kept. "
                "Change its role to 'user' to remove its access instead.", 409)
    email = user.email
    db.delete(user)
    db.commit()
    log_action(db, current_user.id, "user.delete", "user", user_id, request.client.host if request.client else None,
               detail=f"deleted {email}")
    return None
