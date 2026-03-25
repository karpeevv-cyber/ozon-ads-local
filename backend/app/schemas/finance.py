from pydantic import BaseModel


class FinanceRowResponse(BaseModel):
    day: str
    opening_balance: int
    closing_balance: int
    change: int
    sales: int
    fee: int
    acquiring: int
    payments: int
    logistics: int
    returns: int
    storage: int
    marketing: int
    logistics_pct: float


class FinanceSummaryResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    rows: list[FinanceRowResponse]
    totals: dict[str, float]
