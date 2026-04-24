from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyProfileResponse(BaseModel):
    id: int
    name: str
    display_name: str
    is_active: bool
    role: str = "member"
    perf_client_id: str = ""
    perf_client_secret_masked: str = ""
    seller_client_id: str = ""
    seller_api_key_masked: str = ""


class CompanyProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=255)
    perf_client_id: str = ""
    perf_client_secret: str = ""
    seller_client_id: str = ""
    seller_api_key: str = ""
    is_active: bool = True


class CompanyProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=255)
    perf_client_id: str | None = None
    perf_client_secret: str | None = None
    seller_client_id: str | None = None
    seller_api_key: str | None = None
    is_active: bool | None = None


class CompanyProfileListResponse(BaseModel):
    companies: list[CompanyProfileResponse]
