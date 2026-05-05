from fastapi import APIRouter, Query

from app.schemas.bids import (
    ApplyBidRequest,
    ApplyBidResponse,
    AddCampaignCommentRequest,
    AddCampaignCommentResponse,
    BidChangeRecordResponse,
    CampaignCommentRecordResponse,
    TestEntryResponse,
)
from app.services.bid_commands import add_campaign_comment_command, apply_bid_command
from app.services.bid_audit import get_campaign_comments, get_recent_bid_changes, get_test_entries

router = APIRouter(prefix="/bids", tags=["bids"])


@router.get("/recent", response_model=list[BidChangeRecordResponse])
def recent_bid_changes(limit: int = Query(default=20, ge=1, le=200)):
    return [BidChangeRecordResponse(**row) for row in get_recent_bid_changes(limit=limit)]


@router.get("/comments", response_model=list[CampaignCommentRecordResponse])
def campaign_comments(
    company: str | None = Query(default=None),
    campaign_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
):
    return [
        CampaignCommentRecordResponse(**row)
        for row in get_campaign_comments(company=company, campaign_id=campaign_id, limit=limit)
    ]


@router.get("/tests", response_model=list[TestEntryResponse])
def test_entries(
    company: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
):
    return [TestEntryResponse(**row) for row in get_test_entries(company=company, limit=limit)]


@router.post("/apply", response_model=ApplyBidResponse)
def apply_bid(payload: ApplyBidRequest):
    return ApplyBidResponse(
        **apply_bid_command(
            company=payload.company,
            campaign_id=payload.campaign_id,
            sku=payload.sku,
            bid_rub=payload.bid_rub,
            reason=payload.reason,
            comment=payload.comment,
        )
    )


@router.post("/comments", response_model=AddCampaignCommentResponse)
def add_campaign_comment(payload: AddCampaignCommentRequest):
    return AddCampaignCommentResponse(
        **add_campaign_comment_command(
            company=payload.company,
            campaign_id=payload.campaign_id,
            day=payload.day,
            comment=payload.comment,
        )
    )
