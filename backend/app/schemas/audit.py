from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    # Resolved from the `users` table so the log is readable without a second
    # lookup. Null when the row belongs to a deleted user, or to a failed login
    # where no account could be identified.
    user_email: Optional[str] = None
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    # Human-readable rendering of the target, e.g. "user analyst@fraudshield.ai"
    # or "transaction #42". Falls back to a dash when there is no target.
    target_label: Optional[str] = None
    # Free-text detail for auth events: the email attempted, and for failures
    # why it was rejected. Never contains the submitted password.
    detail: Optional[str] = None
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
