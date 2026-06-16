"""
RoyalTDN — Strategy Builder Page (Fase 7, Hito 3).

3-column layout:
  Left  (35%): Indicator palette + Rule constructor
  Center(35%): JSON preview + Backtesting (placeholder)
  Right (30%): Strategy management (save/load/deploy)
"""

import json
from datetime import datetime, timezone

import streamlit as st

from royaltdn.frontend.components.builder_state import (
    INDICATOR_DEFS,
    INDICATOR_MAP,
    NEEDS_VALUE,
    OPERATOR_GROUPS,
    add_entry_condition,
    add_exit_condition,
    add_indicator,
    build_config,
    init_builder_state,
    load_config_into_state,
    remove_entry_condition,
    remove_exit_condition,
    remove_indicator,
    reset_builder,
    update_json_view,
)

from royaltdn.strategy.schema import validate_config

# ── Lazy imports for backtesting (avoid heavy imports at top level) ─────

_BACKTEST_RESULT_KEY = "builder_backtest_result"

# ── Page ────────────────────────────────────────────────────────────────

st.title("🛠️ Strategy Builder")
st.caption("Build your own multi-indicator strategy visually")

init_builder_state()

# ── Helper: condition form widget ───────────────────────────────────────


def _render_condition_form(key_prefix: str, on_add, container):
    """Render a condition builder form inside *container*."""
    indicator_names = [d["name"] for d in INDICATOR_DEFS]

    with container:
        with st.expander("➕ Add Condition", expanded=False):
            ind_name = st.selectbox(
                "Indicator", indicator_names, key=f"{key_prefix}_cond_ind"
            )
            op_group = st.selectbox(
                "Operator category",
                [g["group"] for g in OPERATOR_GROUPS],
                key=f"{key_prefix}_cond_group",
            )
            # Find matching group
            group = next(g for g in OPERATOR_GROUPS if g["group"] == op_group)
            op_keys = [o["key"] for o in group["operators"]]
            op_labels = [o["label"] for o in group["operators"]]
            selected_op = st.selectbox(
                "Operator", op_labels, key=f"{key_prefix}_cond_op"
            )
            op_key = op_keys[op_labels.index(selected_op)]

            val = None
            if op_key in NEEDS_VALUE:
                val = st.number_input(
                    "Value", value=50.0, step=1.0, key=f"{key_prefix}_cond_val"
                )

            if st.button("Add Condition", key=f"{key_prefix}_cond_add"):
                cond = {
                    "indicator": ind_name,
                    "params": {},
                    "operator": op_key,
                }
                if val is not None:
                    cond["value"] = val
                on_add(cond)
                st.rerun()


def _render_condition_list(
    conditions_key: str, logic_key: str, on_remove, title: str, container
):
    """Render a list of conditions with logic selector and remove buttons."""
    conditions = st.session_state[conditions_key]
    with container:
        st.subheader(title)
        st.selectbox(
            "Logic",
            ["AND", "OR"],
            key=logic_key,
            label_visibility="collapsed",
        )

        if not conditions:
            st.caption("No conditions yet")
        else:
            for i, cond in enumerate(conditions):
                val_str = f" = {cond.get('value', '')}" if "value" in cond else ""
                cols = st.columns([5, 1])
                cols[0].markdown(
                    f"**{cond['indicator']}** {cond['operator']}{val_str}"
                )
                if cols[1].button("✕", key=f"{conditions_key}_del_{i}"):
                    on_remove(i)
                    st.rerun()


# ── LEFT COLUMN: Indicator Palette + Rules ────────────────────────────

col_left, col_center, col_right = st.columns([3.5, 3.5, 3])

with col_left:
    st.subheader("📊 Indicators")

    # Indicator selector
    indicator_names = [d["name"] for d in INDICATOR_DEFS]
    sel_ind = st.selectbox(
        "Add Indicator",
        [""] + indicator_names,
        key="builder_add_indicator_sel",
        label_visibility="collapsed",
    )

    if sel_ind:
        ind_def = INDICATOR_MAP.get(sel_ind)
        if ind_def:
            with st.container(border=True):
                st.caption(f"**{ind_def['label']}**")
                params = {}
                for p in ind_def["params"]:
                    key = f"builder_param_{sel_ind}_{p['key']}"
                    if p["type"] == "int":
                        params[p["key"]] = st.number_input(
                            p["label"],
                            value=p["default"],
                            min_value=p.get("min", 1),
                            max_value=p.get("max", 999),
                            step=1,
                            key=key,
                        )
                    elif p["type"] == "float":
                        params[p["key"]] = st.number_input(
                            p["label"],
                            value=float(p["default"]),
                            min_value=float(p.get("min", 0)),
                            max_value=float(p.get("max", 999)),
                            step=float(p.get("step", 0.1)),
                            format="%.3f" if p.get("step", 0.1) < 0.01 else "%.2f",
                            key=key,
                        )
                    elif p["type"] == "select":
                        params[p["key"]] = st.selectbox(
                            p["label"], p["options"], index=p["options"].index(p["default"]), key=key,
                        )
                source = params.pop("source", "close") if "source" in [q["key"] for q in ind_def["params"]] else "close"

                if st.button("➕ Add to Strategy", key="builder_add_indicator_btn"):
                    add_indicator(sel_ind, params, source)
                    update_json_view()
                    st.rerun()

    st.divider()

    # Added indicators list
    for ind in st.session_state.builder_indicators:
        cols = st.columns([5, 1])
        ind_def = INDICATOR_MAP.get(ind["type"])
        label = ind_def["label"] if ind_def else ind["type"]
        param_str = ", ".join(f"{k}={v}" for k, v in ind["params"].items())
        cols[0].markdown(f"**{ind['type']}** {param_str}")
        if cols[1].button("✕", key=f"builder_del_ind_{ind['id']}"):
            remove_indicator(ind["id"])
            update_json_view()
            st.rerun()

    # Rules
    st.divider()
    _render_condition_form(
        "entry",
        add_entry_condition,
        st.container(),
    )
    _render_condition_list(
        "builder_entry_conditions",
        "builder_entry_logic",
        remove_entry_condition,
        "📈 Entry Rules",
        st.container(),
    )

    st.divider()
    _render_condition_form(
        "exit",
        add_exit_condition,
        st.container(),
    )
    _render_condition_list(
        "builder_exit_conditions",
        "builder_exit_logic",
        remove_exit_condition,
        "📉 Exit Rules",
        st.container(),
    )

    # Update config button
    st.divider()
    if st.button("🔄 Refresh Config", use_container_width=True, type="primary"):
        update_json_view()
        st.success("Config updated")

# ── CENTER COLUMN: JSON preview + Backtesting placeholder ─────────────

with col_center:
    st.subheader("📝 Config Preview")

    # JSON view
    json_str = st.session_state.get("builder_json_str", "{}")
    st.code(json_str, language="json", line_numbers=True)

    # Validate button
    val_col1, val_col2 = st.columns(2)
    with val_col1:
        if st.button("✅ Validate", use_container_width=True):
            cfg = build_config()
            ok, err = validate_config(cfg)
            if ok:
                st.success("Config is valid!")
            else:
                st.error(f"Validation error: {err}")
    with val_col2:
        if st.button("🗑️ Reset", use_container_width=True):
            reset_builder()
            st.rerun()

    st.divider()
    st.subheader("📈 Backtesting")

    # Backtest config
    bt_col1, bt_col2 = st.columns(2)
    with bt_col1:
        st.text_input("Symbol", value="SPY", key="builder_symbol",
                      help="Ticker symbol for backtesting")
    with bt_col2:
        st.selectbox(
            "Timeframe",
            ["1min", "5min", "15min", "1H", "4H", "1D"],
            index=5,
            key="builder_timeframe",
        )

    st.selectbox(
        "Period",
        ["1 month", "3 months", "6 months", "1 year", "2 years", "5 years"],
        index=3,
        key="builder_backtest_period",
    )

    # Run backtest button — disabled if no entry conditions
    has_entry_conds = len(st.session_state.get("builder_entry_conditions", [])) > 0
    if st.button("▶️ Run Backtest", use_container_width=True, disabled=not has_entry_conds):
        cfg = build_config()
        ok, err = validate_config(cfg)
        if not ok:
            st.error(f"Config invalid: {err}")
        else:
            with st.spinner("Downloading data & running backtest..."):
                try:
                    from royaltdn.strategy.backtesting import run_backtest
                    result = run_backtest(
                        config=cfg,
                        symbol=st.session_state.builder_symbol,
                        timeframe=st.session_state.builder_timeframe,
                        period=st.session_state.builder_backtest_period,
                    )
                    st.session_state[_BACKTEST_RESULT_KEY] = result
                except Exception as e:
                    st.error(f"Backtest error: {e}")

    if not has_entry_conds:
        st.caption("Add entry conditions to run backtest")

    # Show backtest results
    bt_result = st.session_state.get(_BACKTEST_RESULT_KEY)
    if bt_result:
        st.divider()
        metrics = bt_result.get("metrics", {})
        if bt_result.get("error"):
            st.warning(bt_result["error"])

        if metrics and "error" not in metrics:
            from royaltdn.frontend.components.backtest_charts import (
                plot_drawdown,
                plot_equity_curve,
                plot_monthly_heatmap,
                plot_trade_distribution,
                render_metrics_cards,
            )

            # Metrics cards
            render_metrics_cards(metrics)

            # Charts
            dates = bt_result.get("dates", [])
            equity_series = bt_result.get("equity_series", [])
            bh_equity = bt_result.get("buy_hold_equity", [])
            drawdown_series = bt_result.get("drawdown_series", [])
            trades = bt_result.get("trades", [])
            daily_returns = bt_result.get("daily_returns", [])

            fig_eq = plot_equity_curve(equity_series, bh_equity, dates)
            st.plotly_chart(fig_eq, width='stretch')

            dd_col, dist_col = st.columns(2)
            with dd_col:
                fig_dd = plot_drawdown(drawdown_series, dates)
                st.plotly_chart(fig_dd, width='stretch')
            with dist_col:
                fig_dist = plot_trade_distribution(trades)
                st.plotly_chart(fig_dist, width='stretch')

            # Monthly heatmap
            fig_hm = plot_monthly_heatmap(daily_returns, dates)
            st.plotly_chart(fig_hm, width='stretch')

            # Trades table
            if trades:
                with st.expander("📋 Trade List", expanded=False):
                    st.dataframe(trades, width='stretch')

# ── RIGHT COLUMN: Strategy Management ──────────────────────────────────

with col_right:
    st.subheader("💾 Strategy Management")

    # Name
    st.text_input("Strategy Name", key="builder_name",
                  placeholder="my_rsi_strategy")

    # Save
    if st.button("💾 Save Strategy", use_container_width=True, type="primary"):
        cfg = build_config()
        ok, err = validate_config(cfg)
        if not ok:
            st.error(f"Cannot save — invalid config: {err}")
        else:
            try:
                from royaltdn.strategy.strategy_store import StrategyStore
                store = StrategyStore()
                path = store.save(cfg)
                st.session_state.builder_saved = True
                st.success(f"Saved! {path.split('/')[-1]}")
            except Exception as e:
                st.error(f"Save error: {e}")

    # Load
    st.divider()
    st.caption("Load saved strategy")
    try:
        from royaltdn.strategy.strategy_store import StrategyStore
        store = StrategyStore()
        names = store.list_names()
    except Exception:
        names = []
        st.warning("Strategy store unavailable")

    if names:
        selected = st.selectbox(
            "Select strategy", [""] + names, key="builder_load_sel",
            label_visibility="collapsed",
        )
        if selected:
            if st.button("📂 Load", use_container_width=True, key="builder_load_btn"):
                cfg = store.load(selected)
                if cfg:
                    load_config_into_state(cfg)
                    st.success(f"Loaded '{selected}'")
                    st.rerun()
                else:
                    st.error(f"Could not load '{selected}'")
    else:
        st.caption("No saved strategies yet")

    # Deploy (placeholder — Hito 5)
    st.divider()
    st.subheader("🚀 Deploy")
    if st.button("▶️ Deploy to Paper Trading", use_container_width=True, disabled=True):
        pass  # placeholder — Hito 5
    st.caption("Deployment will be available in Phase 5")

    # Risk management
    st.divider()
    st.subheader("⚠️ Risk Management")
    with st.container(border=True):
        st.number_input(
            "Stop Loss %", value=2.0, min_value=0.0, max_value=100.0,
            step=0.1, key="builder_stop_loss",
        )
        st.number_input(
            "Take Profit %", value=5.0, min_value=0.0, max_value=100.0,
            step=0.1, key="builder_take_profit",
        )
        st.number_input(
            "Max Position Size", value=1.0, min_value=0.0, max_value=100.0,
            step=0.1, key="builder_max_pos",
        )
        st.number_input(
            "Max Daily Loss", value=0.1, min_value=0.0, max_value=100.0,
            step=0.01, format="%.2f", key="builder_max_loss",
        )

    # Status indicators
    if st.session_state.get("builder_saved"):
        st.success("✅ Strategy saved")
    if st.session_state.get("builder_deployed"):
        st.success("✅ Strategy deployed")
