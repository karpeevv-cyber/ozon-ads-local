# Legacy Area

This directory represents the legacy runtime boundary for the existing Streamlit application.

For now, the current Streamlit source files still live in the repository root and continue to be treated as the active legacy implementation.

Planned next step:

- move or mirror the legacy runtime into `legacy/streamlit` only when the new backend bootstrap is stable and imports are mapped safely

Until then, files in the repository root that power Streamlit are considered legacy code.
