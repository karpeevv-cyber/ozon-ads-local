from __future__ import annotations

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.organization import MarketplaceCredential, Organization
from app.models.user import OrganizationMembership, User
from app.services.company_config import default_company_from_env, load_company_configs


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return slug or "default"


def mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _get_active_credential(organization: Organization) -> MarketplaceCredential | None:
    for credential in organization.credentials:
        if credential.provider == "ozon" and credential.is_active:
            return credential
    return organization.credentials[0] if organization.credentials else None


def company_config_from_org(organization: Organization) -> dict[str, str]:
    credential = _get_active_credential(organization)
    if credential is None:
        return {
            "perf_client_id": "",
            "perf_client_secret": "",
            "seller_client_id": "",
            "seller_api_key": "",
        }
    return {
        "perf_client_id": credential.perf_client_id,
        "perf_client_secret": credential.perf_client_secret,
        "seller_client_id": credential.seller_client_id,
        "seller_api_key": credential.seller_api_key,
    }


def seed_companies_from_env(db: Session) -> None:
    if db.query(Organization).first() is not None:
        return

    configs = load_company_configs()
    if not configs:
        default_config = default_company_from_env()
        configs = {"default": default_config} if any(default_config.values()) else {}
    if not configs:
        return

    admin_users = db.query(User).filter(User.is_admin.is_(True)).all()
    for name, config in sorted(configs.items()):
        slug = normalize_slug(name)
        organization = Organization(slug=slug, name=name or slug, is_active=True)
        db.add(organization)
        db.flush()
        db.add(
            MarketplaceCredential(
                organization_id=organization.id,
                provider="ozon",
                perf_client_id=config.get("perf_client_id", ""),
                perf_client_secret=config.get("perf_client_secret", ""),
                seller_client_id=config.get("seller_client_id", ""),
                seller_api_key=config.get("seller_api_key", ""),
                is_active=True,
            )
        )
        for user in admin_users:
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="admin",
                )
            )
    db.commit()


def list_accessible_companies(db: Session, user: User) -> list[tuple[Organization, str]]:
    seed_companies_from_env(db)
    query = (
        db.query(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .options(joinedload(Organization.credentials))
        .filter(OrganizationMembership.user_id == user.id)
        .order_by(Organization.name.asc())
    )
    rows = query.all()
    if rows or not user.is_admin:
        return rows

    organizations = (
        db.query(Organization)
        .options(joinedload(Organization.credentials))
        .order_by(Organization.name.asc())
        .all()
    )
    for organization in organizations:
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="admin",
            )
        )
    db.commit()
    return [(organization, "admin") for organization in organizations]


def list_active_company_configs(db: Session) -> dict[str, dict[str, str]]:
    seed_companies_from_env(db)
    organizations = (
        db.query(Organization)
        .options(joinedload(Organization.credentials))
        .filter(Organization.is_active.is_(True))
        .order_by(Organization.slug.asc())
        .all()
    )
    return {organization.slug: company_config_from_org(organization) for organization in organizations}


def get_company_by_name(db: Session, name: str) -> Organization | None:
    slug = normalize_slug(name)
    return (
        db.query(Organization)
        .options(joinedload(Organization.credentials))
        .filter(or_(Organization.slug == slug, Organization.name == name))
        .first()
    )


def get_company_for_user(db: Session, user: User, company_id: int) -> tuple[Organization, OrganizationMembership]:
    row = (
        db.query(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .options(joinedload(Organization.credentials))
        .filter(Organization.id == company_id, OrganizationMembership.user_id == user.id)
        .first()
    )
    if row is None:
        raise LookupError("Company not found")
    return row


def create_company(db: Session, user: User, payload) -> Organization:
    slug = normalize_slug(payload.name)
    if db.query(Organization).filter(or_(Organization.slug == slug, Organization.name == payload.name)).first():
        raise ValueError("Company already exists")

    organization = Organization(
        slug=slug,
        name=(payload.display_name or payload.name).strip(),
        is_active=payload.is_active,
    )
    db.add(organization)
    db.flush()
    db.add(
        MarketplaceCredential(
            organization_id=organization.id,
            provider="ozon",
            perf_client_id=(payload.perf_client_id or "").strip(),
            perf_client_secret=(payload.perf_client_secret or "").strip(),
            seller_client_id=(payload.seller_client_id or "").strip(),
            seller_api_key=(payload.seller_api_key or "").strip(),
            is_active=True,
        )
    )
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="admin" if user.is_admin else "owner",
        )
    )
    db.commit()
    db.refresh(organization)
    return get_company_by_name(db, organization.slug) or organization


def update_company(db: Session, user: User, company_id: int, payload) -> Organization:
    organization, membership = get_company_for_user(db, user, company_id)
    if membership.role not in {"admin", "owner"} and not user.is_admin:
        raise PermissionError("Company admin access required")

    if payload.name is not None:
        next_slug = normalize_slug(payload.name)
        duplicate = (
            db.query(Organization)
            .filter(Organization.id != organization.id)
            .filter(or_(Organization.slug == next_slug, Organization.name == payload.name))
            .first()
        )
        if duplicate is not None:
            raise ValueError("Company already exists")
        organization.slug = next_slug
    if payload.display_name is not None:
        organization.name = payload.display_name.strip() or organization.slug
    if payload.is_active is not None:
        organization.is_active = payload.is_active

    credential = _get_active_credential(organization)
    if credential is None:
        credential = MarketplaceCredential(organization_id=organization.id, provider="ozon", is_active=True)
        db.add(credential)

    for field in ["perf_client_id", "perf_client_secret", "seller_client_id", "seller_api_key"]:
        value = getattr(payload, field)
        if value is not None and value != "":
            setattr(credential, field, value.strip())

    db.commit()
    return get_company_by_name(db, organization.slug) or organization
