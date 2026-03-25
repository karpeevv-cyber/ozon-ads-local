# Stabilization Checklist

## Core runtime

- backend starts cleanly
- frontend starts cleanly
- docker compose starts all services
- nginx routes frontend and backend correctly

## Auth

- admin seed works
- login works
- `/api/auth/me` requires token
- unauthenticated UI is blocked by login screen

## Campaigns

- companies list loads
- running campaigns load for selected company
- campaign report loads for selected date range
- parity script passes for at least one real period

## Bids

- recent bid changes load
- campaign comments load
- apply bid works for a known campaign and SKU
- shared legacy log receives the new change

## Stocks

- stocks snapshot loads for selected company
- empty credentials case degrades cleanly

## Storage

- storage snapshot loads from cache
- risk rows render without crashing

## Finance

- finance summary loads for selected period
- totals render

## Safety

- legacy Streamlit still runs
- no destructive changes to legacy data flow
- no production switch yet
