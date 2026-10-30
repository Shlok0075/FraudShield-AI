from pydantic import BaseModel


class KPIResponse(BaseModel):
    total_transactions: int
    fraud_count: int
    suspicious_count: int
    safe_count: int
    fraud_rate: float
    active_alerts: int
    high_risk_users: int


class LabelValue(BaseModel):
    label: str
    value: float


class TrendPoint(BaseModel):
    bucket: str
    transactions: int
    fraud: int


class ModelInfoResponse(BaseModel):
    version: str
    trained_at: str
    precision: float
    recall: float
    f1: float
    roc_auc: float
    pr_auc: float
    predictions_served: int
