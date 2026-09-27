"""
waterfall.py
============
Price Waterfall (List -> Invoice -> Pocket Price) and rule-based segmentation.

The waterfall is THE named consulting framework (McKinsey/Simon-Kucher style):
list price minus on-invoice discounts = invoice price; invoice price minus
off-invoice leakage (rebates, co-op/marketing, freight, cost of payment terms)
= pocket price. Every step here is a SUM/GROUPBY on columns that were
generated explicitly in generate_data.py -- nothing is inferred.

Segmentation is rule-based: volume tier x channel x geography, using the
thresholds already baked into the transaction table (no clustering algorithm
is used anywhere in this file).
"""

import pandas as pd


def load_transactions(path="data/transactions.csv") -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["order_date"])


# ---------------------------------------------------------------------------
# Waterfall bridge (aggregate, whole-book or filtered)
# ---------------------------------------------------------------------------

WATERFALL_STEPS = [
    ("List Revenue", "list_revenue", None),
    ("(-) Invoice Discount", "invoice_discount_leakage", "list_revenue"),
    ("Invoice Revenue", "invoice_revenue", None),
    ("(-) Volume Rebate", "volume_rebate_leakage", "invoice_revenue"),
    ("(-) Co-op / Marketing", "coop_marketing_leakage", "invoice_revenue"),
    ("(-) Freight", "freight_leakage", "invoice_revenue"),
    ("(-) Payment Terms Cost", "payment_terms_leakage", "invoice_revenue"),
    ("Pocket Revenue", "pocket_revenue", None),
]


def build_waterfall_bridge(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a tidy bridge table: step name, $ value, $ delta from list, % of list."""
    list_rev = df["list_revenue"].sum()
    rows = []
    for label, col, _ in WATERFALL_STEPS:
        val = df[col].sum()
        rows.append({
            "step": label,
            "value": round(val, 2),
            "pct_of_list": round(val / list_rev, 4) if list_rev else 0,
        })
    return pd.DataFrame(rows)


def leakage_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """$ and % of total leakage attributable to each deduction category -- pure sums."""
    components = {
        "Invoice Discount": df["invoice_discount_leakage"].sum(),
        "Volume Rebate": df["volume_rebate_leakage"].sum(),
        "Co-op / Marketing": df["coop_marketing_leakage"].sum(),
        "Freight": df["freight_leakage"].sum(),
        "Payment Terms Cost": df["payment_terms_leakage"].sum(),
    }
    total = sum(components.values())
    out = pd.DataFrame([
        {"component": k, "leakage_amount": round(v, 2), "pct_of_total_leakage": round(v / total, 4) if total else 0}
        for k, v in components.items()
    ]).sort_values("leakage_amount", ascending=False)
    return out


# ---------------------------------------------------------------------------
# Rule-based segmentation summary (volume tier x channel x geography)
# ---------------------------------------------------------------------------

def segment_summary(df: pd.DataFrame, group_cols=("tier", "channel", "region")) -> pd.DataFrame:
    g = df.groupby(list(group_cols)).agg(
        line_count=("line_id", "count"),
        total_qty=("qty", "sum"),
        list_revenue=("list_revenue", "sum"),
        invoice_revenue=("invoice_revenue", "sum"),
        pocket_revenue=("pocket_revenue", "sum"),
        total_leakage=("total_leakage", "sum"),
    ).reset_index()

    g["pocket_margin_pct_of_list"] = (g["pocket_revenue"] / g["list_revenue"]).round(4)
    g["leakage_pct_of_list"] = (g["total_leakage"] / g["list_revenue"]).round(4)
    g["avg_pocket_price_realization"] = (g["pocket_revenue"] / g["invoice_revenue"]).round(4)  # pocket as % of invoice
    return g.sort_values("total_leakage", ascending=False)


if __name__ == "__main__":
    df = load_transactions()

    bridge = build_waterfall_bridge(df)
    bridge.to_csv("data/waterfall_bridge.csv", index=False)
    print("--- Price Waterfall Bridge ---")
    print(bridge.to_string(index=False))

    leak = leakage_breakdown(df)
    leak.to_csv("data/leakage_breakdown.csv", index=False)
    print("\n--- Leakage Breakdown ---")
    print(leak.to_string(index=False))

    seg = segment_summary(df)
    seg.to_csv("data/segment_summary.csv", index=False)
    print(f"\n--- Segment Summary ({len(seg)} segments: tier x channel x region) ---")
    print(seg.head(10).to_string(index=False))
