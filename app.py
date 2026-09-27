"""
Pricing & Revenue Leakage Command Center
=========================================
Streamlit dashboard. All figures shown here are pre-computed with plain
arithmetic in src/waterfall.py, src/elasticity.py, and src/scenario.py --
this app only aggregates and visualizes, it does not fit any model.

Run:  streamlit run dashboard/app.py
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from waterfall import load_transactions, build_waterfall_bridge, leakage_breakdown, segment_summary, WATERFALL_STEPS
from elasticity import load_data as load_elasticity_inputs, compute_elasticity_table, product_level_summary
from scenario import build_scenario_table

# ---------------------------------------------------------------------------
# Page config & style
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Pricing & Revenue Leakage Command Center",
    page_icon="\U0001F4B0",
    layout="wide",
)

ACCENT = "#1B4965"
ACCENT_LIGHT = "#5FA8D3"
LEAK_COLOR = "#C1121F"
POCKET_COLOR = "#2A9D8F"
NEUTRAL = "#6C757D"

st.markdown(
    """
    <style>
    .metric-card {background-color:#F5F7FA; padding:1rem; border-radius:0.5rem; border-left:4px solid #1B4965;}
    div[data-testid="stMetricValue"] {font-size: 1.6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_data
def get_transactions():
    return pd.read_csv(os.path.join(DATA_DIR, "transactions.csv"), parse_dates=["order_date"])

@st.cache_data
def get_elasticity():
    txn = get_transactions()
    events = pd.read_csv(os.path.join(DATA_DIR, "price_change_events.csv"), parse_dates=["change_date"])
    elas_events = compute_elasticity_table(txn, events)
    prod_summary = product_level_summary(elas_events)
    return elas_events, prod_summary

df = get_transactions()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

st.sidebar.title("\U0001F4CA Filters")
st.sidebar.caption("Pricing & Revenue Leakage Command Center")

regions = st.sidebar.multiselect("Region", sorted(df["region"].unique()), default=sorted(df["region"].unique()))
channels = st.sidebar.multiselect("Channel", sorted(df["channel"].unique()), default=sorted(df["channel"].unique()))
tiers = st.sidebar.multiselect("Volume Tier", sorted(df["tier"].unique()), default=sorted(df["tier"].unique()))
categories = st.sidebar.multiselect("Product Category", sorted(df["category"].unique()), default=sorted(df["category"].unique()))

date_min, date_max = df["order_date"].min(), df["order_date"].max()
date_range = st.sidebar.date_input("Order Date Range", value=(date_min, date_max), min_value=date_min, max_value=date_max)

st.sidebar.markdown("---")
st.sidebar.caption(
    "All figures are calculated directly from transaction-level data: "
    "SUMs, GROUP BYs, and %Δ/%Δ arithmetic. No clustering or regression models "
    "are used anywhere in this dashboard."
)

filtered = df[
    df["region"].isin(regions)
    & df["channel"].isin(channels)
    & df["tier"].isin(tiers)
    & df["category"].isin(categories)
]
if isinstance(date_range, tuple) and len(date_range) == 2:
    filtered = filtered[
        (filtered["order_date"] >= pd.Timestamp(date_range[0]))
        & (filtered["order_date"] <= pd.Timestamp(date_range[1]))
    ]

if filtered.empty:
    st.warning("No transactions match the current filters. Adjust filters in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Header + top-line KPIs
# ---------------------------------------------------------------------------

st.title("\U0001F4B0 Pricing & Revenue Leakage Command Center")
st.caption("List \u2192 Invoice \u2192 Pocket Price waterfall, rule-based segmentation, and event-based elasticity \u2014 built entirely on plain arithmetic.")

list_rev = filtered["list_revenue"].sum()
invoice_rev = filtered["invoice_revenue"].sum()
pocket_rev = filtered["pocket_revenue"].sum()
total_leak = filtered["total_leakage"].sum()
leak_pct = total_leak / list_rev if list_rev else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("List Revenue", f"${list_rev/1e6:,.1f}M")
k2.metric("Invoice Revenue", f"${invoice_rev/1e6:,.1f}M", f"-{(1-invoice_rev/list_rev):.1%} vs list")
k3.metric("Pocket Revenue", f"${pocket_rev/1e6:,.1f}M", f"-{(1-pocket_rev/list_rev):.1%} vs list")
k4.metric("Total Leakage", f"${total_leak/1e6:,.1f}M", f"{leak_pct:.1%} of list", delta_color="inverse")
k5.metric("Transaction Lines", f"{len(filtered):,}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4 = st.tabs([
    "\U0001F4C9 Price Waterfall",
    "\U0001F5FA\uFE0F Segmentation",
    "\U0001F4C8 Elasticity",
    "\U0001F3AF Scenario Planner",
])

# --- TAB 1: WATERFALL -------------------------------------------------------
with tab1:
    st.subheader("Price Waterfall Bridge: List \u2192 Invoice \u2192 Pocket")
    st.caption("List Price \u2212 On-Invoice Discounts = Invoice Price \u2212 Off-Invoice Leakage (rebates, co-op, freight, payment terms) = Pocket Price")

    bridge = build_waterfall_bridge(filtered)

    # Build waterfall chart (Plotly native waterfall)
    measures = []
    values = []
    labels = []
    for i, row in bridge.iterrows():
        label = row["step"]
        labels.append(label)
        if label in ("List Revenue", "Invoice Revenue", "Pocket Revenue"):
            measures.append("total" if label != "List Revenue" else "absolute")
            values.append(row["value"])
        else:
            measures.append("relative")
            values.append(-row["value"])

    # Fix: List Revenue should be absolute (start), Invoice/Pocket should be totals
    measures = []
    for label in bridge["step"]:
        if label in ("List Revenue", "Invoice Revenue", "Pocket Revenue"):
            measures.append("total")
        else:
            measures.append("relative")

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measures,
        x=bridge["step"],
        y=values,
        text=[f"${v/1e6:,.1f}M" for v in bridge["value"]],
        textposition="outside",
        connector={"line": {"color": NEUTRAL}},
        increasing={"marker": {"color": POCKET_COLOR}},
        decreasing={"marker": {"color": LEAK_COLOR}},
        totals={"marker": {"color": ACCENT}},
    ))
    fig.update_layout(
        height=480,
        showlegend=False,
        yaxis_title="Revenue ($)",
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("**Leakage Breakdown by Component**")
        leak_bd = leakage_breakdown(filtered)
        fig2 = px.bar(
            leak_bd, x="leakage_amount", y="component", orientation="h",
            text=leak_bd["pct_of_total_leakage"].apply(lambda x: f"{x:.1%}"),
            color_discrete_sequence=[LEAK_COLOR],
        )
        fig2.update_layout(height=320, xaxis_title="Leakage ($)", yaxis_title="", margin=dict(t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)
    with col_b:
        st.markdown("**Waterfall Table**")
        display_bridge = bridge.copy()
        display_bridge["value"] = display_bridge["value"].apply(lambda x: f"${x:,.0f}")
        display_bridge["pct_of_list"] = display_bridge["pct_of_list"].apply(lambda x: f"{x:.1%}")
        st.dataframe(display_bridge, use_container_width=True, hide_index=True, height=320)

# --- TAB 2: SEGMENTATION ----------------------------------------------------
with tab2:
    st.subheader("Rule-Based Segmentation: Volume Tier \u00D7 Channel \u00D7 Geography")
    st.caption("Segments are defined by explicit thresholds (annual quantity tiers, channel, region) \u2014 not a clustering algorithm.")

    seg = segment_summary(filtered)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Leakage % of List by Tier**")
        tier_agg = filtered.groupby("tier").apply(
            lambda g: pd.Series({
                "list_revenue": g["list_revenue"].sum(),
                "total_leakage": g["total_leakage"].sum(),
            }), include_groups=False
        ).reset_index()
        tier_agg["leakage_pct"] = tier_agg["total_leakage"] / tier_agg["list_revenue"]
        fig3 = px.bar(tier_agg.sort_values("leakage_pct", ascending=False), x="tier", y="leakage_pct",
                       text=tier_agg["leakage_pct"].apply(lambda x: f"{x:.1%}"),
                       color_discrete_sequence=[ACCENT])
        fig3.update_layout(height=350, yaxis_tickformat=".0%", xaxis_title="", yaxis_title="Leakage % of List")
        st.plotly_chart(fig3, use_container_width=True)
    with col2:
        st.markdown("**Pocket Revenue by Channel**")
        chan_agg = filtered.groupby("channel")["pocket_revenue"].sum().reset_index().sort_values("pocket_revenue", ascending=False)
        fig4 = px.bar(chan_agg, x="channel", y="pocket_revenue",
                       text=chan_agg["pocket_revenue"].apply(lambda x: f"${x/1e6:,.1f}M"),
                       color_discrete_sequence=[POCKET_COLOR])
        fig4.update_layout(height=350, xaxis_title="", yaxis_title="Pocket Revenue ($)")
        st.plotly_chart(fig4, use_container_width=True)

    st.markdown("**Full Segment Table** (sorted by total leakage, highest first)")
    display_seg = seg.copy()
    for c in ["list_revenue", "invoice_revenue", "pocket_revenue", "total_leakage"]:
        display_seg[c] = display_seg[c].apply(lambda x: f"${x:,.0f}")
    for c in ["pocket_margin_pct_of_list", "leakage_pct_of_list", "avg_pocket_price_realization"]:
        display_seg[c] = display_seg[c].apply(lambda x: f"{x:.1%}")
    st.dataframe(display_seg, use_container_width=True, hide_index=True, height=400)

    st.markdown("#### Volume Tier Definitions (rule-based thresholds)")
    st.table(pd.DataFrame({
        "Tier": ["Tier 1 \u2014 Strategic", "Tier 2 \u2014 Key", "Tier 3 \u2014 Core", "Tier 4 \u2014 Long Tail"],
        "Annual Quantity Threshold": ["\u2265 500 units/yr", "150\u2013499 units/yr", "40\u2013149 units/yr", "< 40 units/yr"],
        "Base Trade Discount": ["18%", "12%", "7%", "3%"],
    }))

# --- TAB 3: ELASTICITY -------------------------------------------------------
with tab3:
    st.subheader("Price Elasticity from Actual Price-Change Events")
    st.caption("Elasticity = %\u0394 Quantity \u00F7 %\u0394 Price, computed from 45-day pre/post windows around each logged list-price change. No regression is fit \u2014 this is arc elasticity around observed events.")

    elas_events, prod_elas = get_elasticity()

    if elas_events.empty:
        st.info("No price-change events fall within the current filters.")
    else:
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown("**Elasticity by Product-Level Event**")
            fig5 = px.bar(
                elas_events.sort_values("elasticity"),
                x="elasticity", y="product_name",
                color="elasticity",
                color_continuous_scale=["#C1121F", "#E9C46A", "#2A9D8F"],
                orientation="h",
                hover_data=["change_date", "pct_price_change", "pct_qty_change"],
            )
            fig5.update_layout(height=420, xaxis_title="Elasticity (%\u0394Qty / %\u0394Price)", yaxis_title="", coloraxis_showscale=False)
            fig5.add_vline(x=-1, line_dash="dash", line_color=NEUTRAL, annotation_text="unit elastic")
            fig5.add_vline(x=1, line_dash="dash", line_color=NEUTRAL)
            st.plotly_chart(fig5, use_container_width=True)
        with col2:
            st.markdown("**Product-Level Average Elasticity**")
            disp = prod_elas.copy()
            st.dataframe(disp[["product_name", "n_events", "avg_elasticity", "interpretation"]],
                         use_container_width=True, hide_index=True, height=420)

        st.markdown("**Underlying Event Detail**")
        detail = elas_events.copy()
        detail["pct_price_change"] = detail["pct_price_change"].apply(lambda x: f"{x:+.1%}")
        detail["pct_qty_change"] = detail["pct_qty_change"].apply(lambda x: f"{x:+.1%}")
        st.dataframe(detail, use_container_width=True, hide_index=True)

        with st.expander("How this is calculated (no black box)"):
            st.markdown(
                """
                For each logged list-price change:
                1. Take average daily units sold in the **45 days before** the change.
                2. Take average daily units sold in the **45 days after** the change.
                3. `%Δ Quantity = (post_avg − pre_avg) / pre_avg`
                4. `Elasticity = %Δ Quantity ÷ %Δ Price`

                A value below -1 (or above +1 in magnitude) means demand is **elastic** \u2014
                customers meaningfully change how much they buy when price moves.
                Between -1 and 1 means demand is **inelastic**.
                """
            )

# --- TAB 4: SCENARIO PLANNER -------------------------------------------------
with tab4:
    st.subheader("Scenario Planner: Price Change \u2192 Margin Impact")
    st.caption("Plain arithmetic: new_qty = current_qty \u00D7 (1 + elasticity \u00D7 %Δprice); margin impact = projected pocket revenue \u2212 current pocket revenue.")

    scenario_pct = st.slider("Price Change Scenario (%)", min_value=-20, max_value=20, value=5, step=1) / 100

    scenario_table = build_scenario_table(scenario_pct)
    st.info(f"Applied elasticity: **{scenario_table['applied_elasticity'].iloc[0]}** \u2014 {scenario_table.attrs.get('elasticity_source', '')}")

    total_current = scenario_table["current_pocket_revenue"].sum()
    total_projected = scenario_table["projected_pocket_revenue"].sum()
    total_impact = scenario_table["margin_impact_$"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Pocket Revenue", f"${total_current/1e6:,.1f}M")
    c2.metric("Projected Pocket Revenue", f"${total_projected/1e6:,.1f}M")
    c3.metric("Total Margin Impact", f"${total_impact/1e6:+,.2f}M", f"{total_impact/total_current:+.1%}")

    st.markdown("**Top / Bottom Segments by Margin Impact**")
    n_show = st.slider("Segments to show", 5, 30, 10)
    top_bottom = pd.concat([
        scenario_table.head(n_show // 2),
        scenario_table.tail(n_show // 2),
    ]).drop_duplicates()

    fig6 = px.bar(
        top_bottom.sort_values("margin_impact_$"),
        x="margin_impact_$",
        y=top_bottom.apply(lambda r: f"{r['tier'][:6]} | {r['channel']} | {r['region']}", axis=1),
        orientation="h",
        color="margin_impact_$",
        color_continuous_scale=["#C1121F", "#E9C46A", "#2A9D8F"],
    )
    fig6.update_layout(height=450, xaxis_title="Margin Impact ($)", yaxis_title="", coloraxis_showscale=False)
    st.plotly_chart(fig6, use_container_width=True)

    st.markdown("**Full Scenario Table**")
    display_scenario = scenario_table.copy()
    for c in ["current_pocket_revenue", "projected_pocket_revenue", "margin_impact_$"]:
        display_scenario[c] = display_scenario[c].apply(lambda x: f"${x:,.0f}")
    display_scenario["price_change_pct"] = display_scenario["price_change_pct"].apply(lambda x: f"{x:+.0%}")
    display_scenario["margin_impact_%"] = display_scenario["margin_impact_%"].apply(lambda x: f"{x:+.1%}")
    st.dataframe(display_scenario, use_container_width=True, hide_index=True, height=400)

    csv = scenario_table.to_csv(index=False).encode("utf-8")
    st.download_button("\U0001F4E5 Download Scenario Table (CSV)", csv, f"scenario_{int(scenario_pct*100):+d}pct.csv", "text/csv")

st.markdown("---")
st.caption("Pricing & Revenue Leakage Command Center \u2014 built with Streamlit + Plotly. All calculations are transparent, reproducible SQL-style aggregations and %Δ/%Δ arithmetic (see src/ for source).")
