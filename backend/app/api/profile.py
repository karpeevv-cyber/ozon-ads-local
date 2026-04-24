from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.repositories.companies import (
    company_config_from_org,
    create_company,
    list_accessible_companies,
    mask_secret,
    update_company,
)
from app.schemas.profile import (
    CompanyProfileCreateRequest,
    CompanyProfileListResponse,
    CompanyProfileResponse,
    CompanyProfileUpdateRequest,
)

router = APIRouter(prefix="/profile", tags=["profile"])


def serialize_company(organization: Organization, role: str = "member") -> CompanyProfileResponse:
    config = company_config_from_org(organization)
    return CompanyProfileResponse(
        id=organization.id,
        name=organization.slug,
        display_name=organization.name,
        is_active=organization.is_active,
        role=role,
        perf_client_id=config.get("perf_client_id", ""),
        perf_client_secret_masked=mask_secret(config.get("perf_client_secret", "")),
        seller_client_id=config.get("seller_client_id", ""),
        seller_api_key_masked=mask_secret(config.get("seller_api_key", "")),
    )


@router.get("/companies", response_model=CompanyProfileListResponse)
def companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyProfileListResponse:
    rows = list_accessible_companies(db, current_user)
    return CompanyProfileListResponse(
        companies=[serialize_company(organization, role) for organization, role in rows]
    )


@router.post("/companies", response_model=CompanyProfileResponse, status_code=status.HTTP_201_CREATED)
def add_company(
    payload: CompanyProfileCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyProfileResponse:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    try:
        organization = create_company(db, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return serialize_company(organization, "admin")


@router.patch("/companies/{company_id}", response_model=CompanyProfileResponse)
def edit_company(
    company_id: int,
    payload: CompanyProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyProfileResponse:
    try:
        organization = update_company(db, current_user, company_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return serialize_company(organization, "admin" if current_user.is_admin else "owner")
