# Data Model

## Purpose

The new backend must replace active file-based state currently stored in:

- `bid_changes.csv`
- `campaign_comments.csv`
- `ui_state_cache.pkl`
- `stocks_*.pkl`
- `storage_*.pkl`
- `trends_snapshot_cache_*.pkl`
- `unit_economics_products_*.csv`

The database model below is intentionally centered on the current product behavior, not on a hypothetical future rewrite.

## Core Entities

### Users

- `users`
  - id
  - email
  - password_hash
  - full_name
  - is_active
  - is_admin
  - created_at
  - updated_at

### Organizations

- `organizations`
  - id
  - slug
  - name
  - is_active
  - created_at
  - updated_at

- `organization_memberships`
  - id
  - organization_id
  - user_id
  - role
  - created_at

### Marketplace Credentials

- `marketplace_credentials`
  - id
  - organization_id
  - provider
  - perf_client_id
  - perf_client_secret
  - seller_client_id
  - seller_api_key
  - is_active
  - created_at
  - updated_at

## Campaign Domain

- `campaigns`
  - id
  - organization_id
  - external_campaign_id
  - title
  - state
  - last_synced_at
  - created_at
  - updated_at

- `campaign_products`
  - id
  - campaign_id
  - sku
  - title
  - current_bid_micro
  - raw_payload_json
  - last_synced_at

- `campaign_daily_metrics`
  - id
  - campaign_id
  - day
  - views
  - clicks
  - money_spent
  - click_price
  - orders
  - orders_money_ads
  - total_revenue
  - ordered_units
  - total_drr_pct
  - raw_ads_json
  - raw_seller_json
  - created_at

## Bids Domain

- `bid_changes`
  - id
  - organization_id
  - campaign_id
  - sku
  - old_bid_micro
  - new_bid_micro
  - reason
  - comment
  - source
  - created_by_user_id
  - created_at

- `campaign_comments`
  - id
  - organization_id
  - campaign_id
  - comment
  - comment_day
  - created_by_user_id
  - created_at

This replaces both bid log CSV and campaign comment CSV while preserving the audit trail.

## Analytics State

- `saved_views`
  - id
  - organization_id
  - user_id
  - module
  - name
  - filters_json
  - columns_json
  - sort_json
  - created_at
  - updated_at

- `refresh_jobs`
  - id
  - organization_id
  - module
  - status
  - requested_by_user_id
  - started_at
  - finished_at
  - error_text

This replaces UI session-ish persistence that currently leaks into `ui_state_cache.pkl`.

## Stocks And Storage

- `stock_snapshots`
  - id
  - organization_id
  - snapshot_key
  - captured_at
  - payload_json

- `stock_review_items`
  - id
  - organization_id
  - snapshot_id
  - sku
  - decision
  - order_qty
  - note
  - updated_by_user_id
  - updated_at

- `storage_snapshots`
  - id
  - organization_id
  - snapshot_key
  - captured_at
  - payload_json

## Trends

- `trend_snapshots`
  - id
  - organization_id
  - mode
  - date_from
  - date_to
  - signature
  - payload_json
  - captured_at

## Unit Economics

- `unit_economics_products`
  - id
  - organization_id
  - sku
  - name
  - tea_cost
  - package_cost
  - label_cost
  - packing_cost
  - updated_at

## Migration Priority

### First persistence targets

1. `organizations`
2. `marketplace_credentials`
3. `campaigns`
4. `campaign_products`
5. `campaign_daily_metrics`
6. `bid_changes`
7. `campaign_comments`

These are enough to support the first end-to-end campaigns flow and bid history without relying on local files.
