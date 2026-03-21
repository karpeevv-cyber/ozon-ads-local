# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path
import pickle

import altair as alt
import pandas as pd
import streamlit as st

from trend_data import build_trend_snapshot
from trend_sources import ENABLE_QUERY_SIGNALS


def _make_item_option_label(item: dict, mode: str) -> str:
    title = str(item.get("title", "") or "Unknown")
    trend = float(item.get("trend_score", 0) or 0)
    confidence = float(item.get("confidence_score", 0) or 0)
    risk = float(item.get("risk_score", 0) or 0)
    if mode == "Ниши":
        size = int(item.get("products_count", 0) or 0)
        return f"{title} | тренд {trend:.0f} | conf {confidence:.0f} | size {size} | risk {risk:.0f}"
    revenue = float(item.get("revenue", 0) or 0)
    return f"{title} | тренд {trend:.0f} | conf {confidence:.0f} | выручка {revenue:.0f} | risk {risk:.0f}"


def render_trends_tab(
    *,
    date_from: date,
    date_to: date,
    seller_client_id: str | None,
    seller_api_key: str | None,
    company_name: str | None,
) -> None:
    st.subheader("Поиск трендов")
    st.caption("MVP: explainable trend discovery for niches and product ideas.")

    if not seller_client_id or not seller_api_key:
        st.warning("Seller creds are missing for selected company.")
        return

    col_mode, col_horizon, col_filter, col_refresh = st.columns([1.0, 1.0, 1.7, 0.9])
    with col_mode:
        mode = st.radio(
            "View",
            options=["Ниши", "Товары"],
            horizontal=True,
            key="trends_mode",
        )
    with col_horizon:
        horizon_label = st.selectbox(
            "Горизонт",
            options=["2-4 weeks", "1-3 months", "3-6 months"],
            index=1,
            key="trends_horizon",
        )
    with col_filter:
        search_filter = st.text_input(
            "Фильтр по названию",
            value=st.session_state.get("trends_search_filter", ""),
            key="trends_search_filter",
            placeholder="Например, чай, свечи, органайзер",
        )
    with col_refresh:
        refresh_cache = st.button("Refresh cache", key="trends_refresh_cache")

    run_analysis = st.button("Найти тренды", type="primary", key="trends_run")

    snapshot_key = "trends_snapshot"
    snapshot_meta_key = "trends_snapshot_meta"
    snapshot_source_key = "trends_snapshot_source"
    cache_path = Path(f"trends_snapshot_cache_{(seller_client_id or 'default').strip()}.pkl")
    current_signature = (
        str(company_name or ""),
        str(date_from),
        str(date_to),
        horizon_label,
        search_filter.strip().lower(),
    )

    if refresh_cache:
        st.session_state.pop(snapshot_key, None)
        st.session_state.pop(snapshot_meta_key, None)
        st.session_state.pop(snapshot_source_key, None)
        try:
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass

    if snapshot_key not in st.session_state and cache_path.exists():
        try:
            with cache_path.open("rb") as f:
                cached_payload = pickle.load(f) or {}
            if cached_payload.get("signature") == current_signature:
                st.session_state[snapshot_key] = cached_payload.get("snapshot")
                st.session_state[snapshot_meta_key] = cached_payload.get("signature")
                st.session_state[snapshot_source_key] = "cache"
        except Exception:
            pass

    if run_analysis:
        with st.spinner("Анализирую внутренние сигналы спроса и query-данные..."):
            try:
                snapshot = build_trend_snapshot(
                    date_from=date_from,
                    date_to=date_to,
                    seller_client_id=seller_client_id,
                    seller_api_key=seller_api_key,
                    horizon=horizon_label,
                    company_name=company_name,
                    search_filter=search_filter,
                )
                st.session_state[snapshot_key] = snapshot
                st.session_state[snapshot_meta_key] = current_signature
                st.session_state[snapshot_source_key] = "fresh"
                try:
                    with cache_path.open("wb") as f:
                        pickle.dump({"signature": current_signature, "snapshot": snapshot}, f)
                except Exception:
                    pass
            except Exception as exc:
                st.error(f"Trend analysis failed: {exc}")
                return

    if st.session_state.get(snapshot_meta_key) != current_signature:
        st.info("Настройки изменились. Нажмите `Найти тренды`, чтобы пересчитать результаты.")
        return

    snapshot = st.session_state.get(snapshot_key)
    if not snapshot:
        st.info("Нажмите `Найти тренды`, чтобы построить первые гипотезы.")
        return

    for error in snapshot.get("errors", []):
        st.warning(error)

    meta = snapshot.get("meta", {}) or {}
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Период анализа", f'{meta.get("period_days", 0)} days')
    kpi2.metric("Товаров просмотрено", int(meta.get("products_scanned", 0) or 0))
    kpi3.metric("SKU c query-сигналом", int(meta.get("query_signal_products", 0) or 0))
    kpi4.metric("External seeds", int(meta.get("external_seed_terms", 0) or 0))
    if meta.get("generated_at"):
        snapshot_source = st.session_state.get(snapshot_source_key, "unknown")
        source_label = "из кэша" if snapshot_source == "cache" else "свежий расчет" if snapshot_source == "fresh" else "неизвестно"
        st.caption(f"Snapshot: {source_label} | {meta.get('generated_at')}")
    if not ENABLE_QUERY_SIGNALS:
        st.caption("Product-queries signal is running in safe fallback mode: disabled by default because the current Ozon endpoint is unstable.")

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        min_confidence = st.slider("Min confidence", min_value=0, max_value=100, value=35, step=5)
    with filter_col2:
        max_risk = st.slider("Max risk", min_value=0, max_value=100, value=70, step=5)
    with filter_col3:
        min_cluster_size = st.slider("Min niche size", min_value=1, max_value=10, value=1, step=1)

    controls_col1, controls_col2 = st.columns(2)
    with controls_col1:
        if mode == "Ниши":
            sort_choice = st.selectbox(
                "Sort by",
                options=["Overall rank", "Trend", "Confidence", "Cluster size", "Top revenue"],
                index=0,
                key="trends_sort_niches",
            )
        else:
            sort_choice = st.selectbox(
                "Sort by",
                options=["Trend", "Confidence", "Revenue", "Search signal"],
                index=0,
                key="trends_sort_products",
            )
    with controls_col2:
        max_rows = st.slider("Rows to show", min_value=5, max_value=30, value=15, step=5)

    items = snapshot.get("niches", []) if mode == "Ниши" else snapshot.get("products", [])
    if mode == "Ниши":
        items = [
            item for item in items
            if float(item.get("confidence_score", 0) or 0) >= min_confidence
            and float(item.get("risk_score", 0) or 0) <= max_risk
            and int(item.get("products_count", 0) or 0) >= min_cluster_size
        ]
    else:
        items = [
            item for item in items
            if float(item.get("confidence_score", 0) or 0) >= min_confidence
            and float(item.get("risk_score", 0) or 0) <= max_risk
        ]
    if not items:
        st.info("По текущим фильтрам подходящих гипотез не найдено.")
        return

    df = pd.DataFrame(items)
    if mode == "Ниши":
        visible_cols = [
            "title",
            "products_count",
            "trend_score",
            "confidence_score",
            "competition_score",
            "risk_score",
            "demand_signal",
            "top_product_revenue",
            "reason_tags",
            "explanation",
        ]
    else:
        visible_cols = [
            "title",
            "niche_id",
            "trend_score",
            "confidence_score",
            "competition_score",
            "risk_score",
            "demand_signal",
            "search_signal" if "search_signal" in df.columns else None,
            "revenue" if "revenue" in df.columns else None,
            "ordered_units" if "ordered_units" in df.columns else None,
            "reason_tags" if "reason_tags" in df.columns else None,
            "explanation",
        ]
    visible_cols = [col for col in visible_cols if col in df.columns]
    if mode == "Ниши":
        sort_map = {
            "Overall rank": ["niche_rank_score", "trend_score", "confidence_score"],
            "Trend": ["trend_score", "confidence_score"],
            "Confidence": ["confidence_score", "trend_score"],
            "Cluster size": ["products_count", "trend_score"],
            "Top revenue": ["top_product_revenue", "trend_score"],
        }
    else:
        sort_map = {
            "Trend": ["trend_score", "confidence_score"],
            "Confidence": ["confidence_score", "trend_score"],
            "Revenue": ["revenue", "trend_score"],
            "Search signal": ["search_signal", "trend_score"],
        }
    sort_cols = [col for col in sort_map.get(sort_choice, ["trend_score"]) if col in df.columns]
    if not sort_cols:
        sort_cols = ["trend_score"]
    export_df = df.sort_values(sort_cols, ascending=False).copy()
    export_view_df = export_df[visible_cols].copy()

    summary_col1, summary_col2, summary_col3 = st.columns(3)
    summary_col1.metric("Filtered rows", len(export_df))
    summary_col2.metric("Avg confidence", f"{export_df['confidence_score'].mean():.0f}" if "confidence_score" in export_df.columns else "0")
    summary_col3.metric("Avg risk", f"{export_df['risk_score'].mean():.0f}" if "risk_score" in export_df.columns else "0")

    if not export_df.empty:
        top_row = export_df.iloc[0].to_dict()
        top_label = "Best niche now" if mode == "Ниши" else "Best product now"
        st.caption(f"{top_label}: {top_row.get('title', 'Unknown')} | trend {float(top_row.get('trend_score', 0) or 0):.0f} | conf {float(top_row.get('confidence_score', 0) or 0):.0f}")

    export_col1, export_col2 = st.columns([1.2, 4.0])
    with export_col1:
        st.download_button(
            "Export CSV",
            data=export_view_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"trend_{'niches' if mode == 'Ниши' else 'products'}_{str(date_from)}_{str(date_to)}.csv",
            mime="text/csv",
            key=f"trends_export_{mode}",
        )
    st.dataframe(
        export_view_df.head(max_rows),
        width="stretch",
        hide_index=True,
    )

    chart_df = export_df[["title", "trend_score", "confidence_score", "risk_score"]].copy().head(min(max_rows, 10))
    chart = (
        alt.Chart(chart_df)
        .transform_fold(
            ["trend_score", "confidence_score", "risk_score"],
            as_=["metric", "value"],
        )
        .mark_bar()
        .encode(
            x=alt.X("value:Q", title="Score"),
            y=alt.Y("title:N", sort="-x", title=None),
            color=alt.Color("metric:N", title=None),
            row=alt.Row("metric:N", title=None),
        )
        .properties(height=80)
    )
    st.altair_chart(chart, width="stretch")

    detail_items = export_df.to_dict("records")[:max_rows]
    detail_options = {
        _make_item_option_label(item, mode): item
        for item in detail_items
    }
    selected_label = st.selectbox(
        "Детализация",
        options=list(detail_options.keys()),
        index=0,
        key="trends_detail_pick",
    )
    selected_item = detail_options.get(selected_label)
    if not selected_item:
        return

    st.markdown(f"### {selected_item.get('title', 'Unknown')}")
    score_cols = st.columns(4)
    score_cols[0].metric("Trend", selected_item.get("trend_score", 0))
    score_cols[1].metric("Confidence", selected_item.get("confidence_score", 0))
    score_cols[2].metric("Competition", selected_item.get("competition_score", 0))
    score_cols[3].metric("Risk", selected_item.get("risk_score", 0))
    st.write(selected_item.get("summary") or selected_item.get("explanation") or "")
    if selected_item.get("reason_tags"):
        st.caption(f"Reasons: {selected_item.get('reason_tags')}")

    if mode == "Ниши":
        niche_products = [
            item for item in snapshot.get("products", [])
            if str(item.get("niche_id", "")) == str(selected_item.get("id", ""))
        ]
        if niche_products:
            niche_df = pd.DataFrame(niche_products)[
                ["title", "trend_score", "confidence_score", "revenue", "ordered_units", "reason_tags", "explanation"]
            ].sort_values("trend_score", ascending=False).head(10)
            st.markdown("**Top products in this niche**")
            st.dataframe(niche_df, width="stretch", hide_index=True)

    history = selected_item.get("history_points") or []
    if history:
        hist_df = pd.DataFrame(history)
        hist_df["day"] = pd.to_datetime(hist_df["day"], errors="coerce")
        hist_chart = (
            alt.Chart(hist_df)
            .transform_fold(["revenue", "ordered_units"], as_=["metric", "value"])
            .mark_line(point=True)
            .encode(
                x=alt.X("day:T", title="Day"),
                y=alt.Y("value:Q", title="Value"),
                color=alt.Color("metric:N", title=None),
            )
            .properties(height=280)
        )
        st.altair_chart(hist_chart, width="stretch")

    details_col1, details_col2 = st.columns(2)
    with details_col1:
        st.markdown("**Drivers**")
        for driver in selected_item.get("drivers", []):
            st.write(f"- {driver}")
        related_queries = selected_item.get("related_queries", [])
        if related_queries:
            st.markdown("**Related queries**")
            for query in related_queries[:5]:
                query_name = query.get("query", "")
                query_searches = query.get("searches", 0)
                query_growth = query.get("growth", 0)
                st.write(f"- {query_name} | searches {query_searches:.0f} | growth {query_growth:.0f}%")
        external_signals = selected_item.get("external_signals", {})
        if external_signals:
            seed_term = external_signals.get("seed_term", "")
            transliterated_seed = external_signals.get("transliterated_seed", "")
            web_suggestions = external_signals.get("web_suggestions", []) or []
            youtube_suggestions = external_signals.get("youtube_suggestions", []) or []
            shopping_suggestions = external_signals.get("shopping_suggestions", []) or []
            if seed_term:
                st.markdown(f"**External seed**: `{seed_term}`")
            if transliterated_seed:
                st.caption(f"fallback transliteration: {transliterated_seed}")
            if web_suggestions:
                st.markdown("**Google web suggestions**")
                for suggestion in web_suggestions[:5]:
                    st.write(f"- {suggestion}")
            if youtube_suggestions:
                st.markdown("**YouTube suggestions**")
                for suggestion in youtube_suggestions[:5]:
                    st.write(f"- {suggestion}")
            if shopping_suggestions:
                st.markdown("**Shopping suggestions**")
                for suggestion in shopping_suggestions[:5]:
                    st.write(f"- {suggestion}")
    with details_col2:
        st.markdown("**Risks**")
        for risk in selected_item.get("risks", []):
            st.write(f"- {risk}")
        checks = selected_item.get("validation_checks", [])
        if checks:
            st.markdown("**Manual validation**")
            for check in checks:
                st.write(f"- {check}")

    external_sources = snapshot.get("external_sources", [])
    if external_sources:
        st.markdown("**External sources**")
        ext_df = pd.DataFrame(external_sources)
        st.dataframe(ext_df, width="stretch", hide_index=True)

    with st.expander("Methodology and Current Limits"):
        st.write("- Results are based on seller sales history, product catalog data, and external suggestion signals.")
        st.write("- Product-queries are currently disabled by default in runtime because the current Ozon endpoint is unstable.")
        st.write("- Trend score is explainable and rule-based; it is not an ML forecast.")
        st.write("- Use the output as ranked hypotheses for manual validation, not as an autonomous launch recommendation.")
