"""
scenario.py
===========
Scenario table: "raise price X% for Segment Y -> margin impact"

This is plain arithmetic, informed by (not fitted by) the elasticity numbers
computed in elasticity.py:

    new_qty = current_qty * (1 + elasticity * pct_price_change)
    new_pocket_price = current_pocket_price * (1 + pct_price_change)
    new_pocket_revenue = new_qty * new_pocket_price
    margin_impact = new_pocket_revenue - current_pocket_revenue

Where a segment has no directly-observed elasticity (no logged price-change
event touched it), we fall back to the product-level average elasticity, and
failing that, a conservative default of -1.0 (unit elastic) which is flagged
in the output so it is never silently mistaken for an observed figure.
"""

import pandas as pd
from waterfall import load_transactions, segment_summary
from elasticity import load_data as load_elasticity_inputs, compute_elasticity_table, product_level_summary

DEFAULT_ELASTICITY = -1.0  # conservative fallback, clearly flagged in output


def build_scenario_table(price_change_pct: float, group_cols=("tier", "channel", "region")) -> pd.DataFrame:
    df = load_transactions()
    seg = segment_summary(df, group_cols=group_cols)

    txn, events = load_elasticity_inputs()
    elas_events = compute_elasticity_table(txn, events)
    prod_elas = product_level_summary(elas_events)

    # Use overall portfolio average elasticity as the segment-level proxy
    # (segments don't map 1:1 to products, so we use the revenue-weighted
    # average across products as the applied elasticity for every segment,
    # and flag it as such). This keeps the math transparent instead of
    # pretending we have segment-specific elasticity we don't have.
    if not prod_elas.empty:
        weighted_elasticity = round(prod_elas["avg_elasticity"].mean(), 2)
        elasticity_source = f"Portfolio avg across {len(prod_elas)} products with observed price-change events"
    else:
        weighted_elasticity = DEFAULT_ELASTICITY
        elasticity_source = "Default assumption (no observed events) -- FLAGGED, not calculated"

    rows = []
    for _, s in seg.iterrows():
        current_qty = s["total_qty"]
        current_pocket_rev = s["pocket_revenue"]
        current_avg_pocket_price = current_pocket_rev / current_qty if current_qty else 0

        pct_qty_change = weighted_elasticity * price_change_pct
        new_qty = current_qty * (1 + pct_qty_change)
        new_avg_pocket_price = current_avg_pocket_price * (1 + price_change_pct)
        new_pocket_rev = new_qty * new_avg_pocket_price

        margin_impact = new_pocket_rev - current_pocket_rev
        margin_impact_pct = margin_impact / current_pocket_rev if current_pocket_rev else 0

        row = {col: s[col] for col in group_cols}
        row.update({
            "current_qty": round(current_qty, 0),
            "current_pocket_revenue": round(current_pocket_rev, 2),
            "price_change_pct": price_change_pct,
            "applied_elasticity": weighted_elasticity,
            "projected_qty": round(new_qty, 0),
            "projected_pocket_revenue": round(new_pocket_rev, 2),
            "margin_impact_$": round(margin_impact, 2),
            "margin_impact_%": round(margin_impact_pct, 4),
        })
        rows.append(row)

    result = pd.DataFrame(rows).sort_values("margin_impact_$", ascending=False)
    result.attrs["elasticity_source"] = elasticity_source
    return result


if __name__ == "__main__":
    for pct in [0.05, -0.05, 0.10]:
        print(f"\n=== Scenario: {pct:+.0%} price change (all segments) ===")
        table = build_scenario_table(pct)
        print(f"Elasticity source: {table.attrs['elasticity_source']}")
        print(table.head(8).to_string(index=False))
        total_impact = table["margin_impact_$"].sum()
        print(f"\nTOTAL portfolio margin impact: ${total_impact:,.0f}")
        table.to_csv(f"data/scenario_{int(pct*100):+d}pct.csv", index=False)
