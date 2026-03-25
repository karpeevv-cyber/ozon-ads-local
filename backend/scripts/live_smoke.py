from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta

import requests


DEFAULT_BACKEND = "http://127.0.0.1:8000/api"
DEFAULT_FRONTEND = "http://127.0.0.1:3000"


@dataclass
class CheckResult:
    name: str
    status: str
    details: str


def parse_args() -> argparse.Namespace:
    today = date.today()
    week_ago = today - timedelta(days=6)
    parser = argparse.ArgumentParser(description="Live smoke checks for backend/frontend runtime.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend API base URL, for example http://127.0.0.1:8200/api")
    parser.add_argument("--frontend", default="", help="Frontend base URL, for example http://127.0.0.1:3200")
    parser.add_argument("--email", default="admin@example.com", help="Admin email for auth smoke")
    parser.add_argument("--password", default="change-me", help="Admin password for auth smoke")
    parser.add_argument("--company", default="", help="Optional company override")
    parser.add_argument("--date-from", default=week_ago.isoformat(), help="Date from in YYYY-MM-DD")
    parser.add_argument("--date-to", default=today.isoformat(), help="Date to in YYYY-MM-DD")
    parser.add_argument("--timeout", type=int, default=45, help="Request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args()


def expect_status(
    session: requests.Session,
    *,
    name: str,
    method: str,
    url: str,
    expected_status: int,
    timeout: int,
    **kwargs,
) -> tuple[CheckResult, requests.Response | None]:
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
    except Exception as exc:
        return CheckResult(name=name, status="failed", details=f"request error: {exc}"), None
    if response.status_code != expected_status:
        return (
            CheckResult(
                name=name,
                status="failed",
                details=f"expected {expected_status}, got {response.status_code} for {url}",
            ),
            response,
        )
    return CheckResult(name=name, status="passed", details=f"{response.status_code} {url}"), response


def main() -> int:
    args = parse_args()
    backend = args.backend.rstrip("/")
    frontend = args.frontend.rstrip("/")
    session = requests.Session()
    results: list[CheckResult] = []

    health_result, _ = expect_status(
        session,
        name="backend_health",
        method="GET",
        url=f"{backend}/health",
        expected_status=200,
        timeout=args.timeout,
    )
    results.append(health_result)

    me_unauth_result, _ = expect_status(
        session,
        name="auth_me_requires_token",
        method="GET",
        url=f"{backend}/auth/me",
        expected_status=401,
        timeout=args.timeout,
    )
    results.append(me_unauth_result)

    login_result, login_response = expect_status(
        session,
        name="auth_login",
        method="POST",
        url=f"{backend}/auth/login",
        expected_status=200,
        timeout=args.timeout,
        json={"email": args.email, "password": args.password},
    )
    results.append(login_result)
    token = ""
    if login_response is not None and login_response.ok:
        try:
            token = str(login_response.json().get("access_token") or "")
        except Exception:
            token = ""
    if not token:
        results.append(CheckResult(name="auth_token_parse", status="failed", details="access_token missing in login response"))
    else:
        results.append(CheckResult(name="auth_token_parse", status="passed", details="access_token present"))

    me_auth_result, me_auth_response = expect_status(
        session,
        name="auth_me_with_token",
        method="GET",
        url=f"{backend}/auth/me",
        expected_status=200,
        timeout=args.timeout,
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    results.append(me_auth_result)

    selected_company = args.company
    companies_result, companies_response = expect_status(
        session,
        name="campaigns_companies",
        method="GET",
        url=f"{backend}/campaigns/companies",
        expected_status=200,
        timeout=args.timeout,
    )
    results.append(companies_result)
    if not selected_company and companies_response is not None and companies_response.ok:
        try:
            companies = companies_response.json()
            if companies:
                selected_company = str(companies[0].get("name") or "").strip()
        except Exception:
            selected_company = ""
    if not selected_company:
        selected_company = "default"

    api_checks = [
        ("campaigns_running", f"{backend}/campaigns/running?company={requests.utils.quote(selected_company)}"),
        (
            "campaigns_report",
            f"{backend}/campaigns/report?company={requests.utils.quote(selected_company)}&date_from={args.date_from}&date_to={args.date_to}&target_drr_pct=20",
        ),
        ("bids_recent", f"{backend}/bids/recent"),
        ("bids_comments", f"{backend}/bids/comments?company={requests.utils.quote(selected_company)}"),
        ("stocks_snapshot", f"{backend}/stocks/snapshot?company={requests.utils.quote(selected_company)}"),
        ("storage_snapshot", f"{backend}/storage/snapshot?company={requests.utils.quote(selected_company)}"),
        (
            "finance_summary",
            f"{backend}/finance/summary?company={requests.utils.quote(selected_company)}&date_from={args.date_from}&date_to={args.date_to}",
        ),
        (
            "trends_snapshot",
            f"{backend}/trends/snapshot?company={requests.utils.quote(selected_company)}&date_from={args.date_from}&date_to={args.date_to}&horizon=1-3%20months",
        ),
        (
            "unit_economics_summary",
            f"{backend}/unit-economics/summary?company={requests.utils.quote(selected_company)}&date_from={args.date_from}&date_to={args.date_to}",
        ),
        (
            "unit_economics_products",
            f"{backend}/unit-economics/products?company={requests.utils.quote(selected_company)}&date_from={args.date_from}&date_to={args.date_to}",
        ),
    ]
    for name, url in api_checks:
        result, _ = expect_status(
            session,
            name=name,
            method="GET",
            url=url,
            expected_status=200,
            timeout=args.timeout,
        )
        results.append(result)

    if frontend:
        frontend_result, _ = expect_status(
            session,
            name="frontend_root",
            method="GET",
            url=frontend,
            expected_status=200,
            timeout=args.timeout,
        )
        results.append(frontend_result)

    passed = sum(1 for result in results if result.status == "passed")
    failed = len(results) - passed
    summary = {
        "backend": backend,
        "frontend": frontend,
        "company": selected_company,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "passed": passed,
        "failed": failed,
        "results": [result.__dict__ for result in results],
    }

    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Backend: {backend}")
        if frontend:
            print(f"Frontend: {frontend}")
        print(f"Company: {selected_company}")
        print(f"Range: {args.date_from}..{args.date_to}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        for result in results:
            print(f"[{result.status}] {result.name}: {result.details}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
