from fastapi import APIRouter, Query

from app.schemas.finance import FinanceSummaryResponse
from app.services.finance_summary import get_finance_summary

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/summary", response_model=FinanceSummaryResponse)
def finance_summary(
    company: str | None = Query(default=None),
    date_from: str = Query(...),
    date_to: str = Query(...),
):
    return FinanceSummaryResponse(**get_finance_summary(company=company, date_from=date_from, date_to=date_to))
