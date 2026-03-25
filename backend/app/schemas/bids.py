from pydantic import BaseModel


class BidChangeRecordResponse(BaseModel):
    ts_iso: str
    date: str
    campaign_id: str
    sku: str
    old_bid_micro: int | None
    new_bid_micro: int | None
    reason: str
    comment: str


class CampaignCommentRecordResponse(BaseModel):
    ts: str
    day: str
    week: str
    company: str
    campaign_id: str
    comment: str


class TestEntryResponse(BaseModel):
    ts_iso: str
    date: str
    campaign_id: str
    sku: str
    reason: str
    comment: str
    company: str


class ApplyBidRequest(BaseModel):
    company: str | None = None
    campaign_id: str
    sku: str
    bid_rub: float
    reason: str
    comment: str = ""


class ApplyBidResponse(BaseModel):
    company: str
    campaign_id: str
    sku: str
    old_bid_micro: int | None
    new_bid_micro: int
    reason: str
    comment: str
