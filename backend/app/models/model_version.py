from sqlalchemy import String, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModelVersion(Base):
    """PART 11.9. Standalone reference table, no FK from transactions."""
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    trained_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="production")
    dataset_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
