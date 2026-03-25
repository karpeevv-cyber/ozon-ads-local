# Parity Checks

## Campaign report parity

The first migration flow must stay behaviorally aligned with legacy Streamlit calculations.

Use this script to compare the legacy and new campaign report outputs for the same:

- company
- date range

Command:

```bash
python backend/scripts/campaign_report_parity.py --company default --date-from 2026-03-18 --date-to 2026-03-24 --json
```

Expected result:

- `grand_total_match=true`
- `rows_match=true`

If mismatches appear, the JSON output includes per-campaign diffs between:

- legacy `report.py`
- new `backend/app/services/campaign_reporting.py`

This check is the gating step before expanding the campaigns flow further.
