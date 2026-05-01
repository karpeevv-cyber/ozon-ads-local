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
    reverse_logistics: int
    returns: int
    cross_docking: int
    acceptance: int
    errors: int
    storage: int
    marketing: int
    promotion_with_cpo: int
    points_for_reviews: int
    seller_bonuses: int
    check: int
    logistics_pct: float


class FinanceSummaryResponse(BaseModel):
    company: str
    date_from: str
    date_to: str
    rows: list[FinanceRowResponse]
    totals: dict[str, float]
