"""
elasticity.py
=============
Classic price elasticity of demand, computed with plain arithmetic:

    Elasticity = (%Δ Quantity) / (%Δ Price)

For each logged price-change event (data/price_change_events.csv), we compare
average daily unit sales in a window BEFORE the change vs a window AFTER the
change, for that exact product. This is the textbook "arc elasticity around
an actual price change" method used in real pricing analytics -- NOT a
regression fit, NOT an ML model. Every number traces back to a SUM or AVERAGE
of the transaction table.

Window size is configurable (default 45 days pre/post) to give enough volume
to average out day-to-day noise while staying close to the event so the
elasticity reflects that specific price change and not a longer-term trend.
"""

import pandas as pd
import numpy as np

WINDOW_DAYS = 45


def load_data(txn_path="data/transactions.csv", events_path="data/price_change_events.csv"):
    txn = pd.read_csv(txn_path, parse_dates=["order_date"])
    events = pd.read_csv(events_path, parse_dates=["change_date"])
    return txn, events


def compute_elasticity_table(txn: pd.DataFrame, events: pd.DataFrame, window_days: int = WINDOW_DAYS) -> pd.DataFrame:
    results = []

    for _, ev in events.iterrows():
        pid = ev["product_id"]
        change_date = ev["change_date"]
        pct_price_change = ev["pct_change"]

        pre_start = change_date - pd.Timedelta(days=window_days)
        pre_end = change_date
        post_start = change_date
        post_end = change_date + pd.Timedelta(days=window_days)

        prod_txn = txn[txn["product_id"] == pid]

        pre_window = prod_txn[(prod_txn["order_date"] >= pre_start) & (prod_txn["order_date"] < pre_end)]
        post_window = prod_txn[(prod_txn["order_date"] >= post_start) & (prod_txn["order_date"] < post_end)]

        pre_avg_daily_qty = pre_window["qty"].sum() / window_days
        post_avg_daily_qty = post_window["qty"].sum() / window_days

        if pre_avg_daily_qty == 0:
            continue  # can't compute a % change from zero base

        pct_qty_change = (post_avg_daily_qty - pre_avg_daily_qty) / pre_avg_daily_qty

        if pct_price_change == 0:
            continue

        elasticity = pct_qty_change / pct_price_change

        product_name = prod_txn["product_name"].iloc[0] if len(prod_txn) else pid

        results.append({
            "product_id": pid,
            "product_name": product_name,
            "change_date": change_date.date().isoformat(),
            "pct_price_change": pct_price_change,
            "pre_avg_daily_qty": round(pre_avg_daily_qty, 2),
            "post_avg_daily_qty": round(post_avg_daily_qty, 2),
            "pct_qty_change": round(pct_qty_change, 4),
            "elasticity": round(elasticity, 2),
            "interpretation": interpret_elasticity(elasticity),
        })

    return pd.DataFrame(results)


def interpret_elasticity(e: float) -> str:
    """Standard economics thresholds -- no modeling, just classification bands."""
    abs_e = abs(e)
    if abs_e > 1:
        return "Elastic (demand sensitive to price)"
    elif abs_e < 1:
        return "Inelastic (demand relatively insensitive)"
    else:
        return "Unit elastic"


def product_level_summary(elasticity_df: pd.DataFrame) -> pd.DataFrame:
    """Average elasticity per product across all its logged events (simple mean, not a fit)."""
    if elasticity_df.empty:
        return elasticity_df
    summary = (
        elasticity_df.groupby(["product_id", "product_name"])
        .agg(
            n_events=("elasticity", "count"),
            avg_elasticity=("elasticity", "mean"),
        )
        .reset_index()
    )
    summary["avg_elasticity"] = summary["avg_elasticity"].round(2)
    summary["interpretation"] = summary["avg_elasticity"].apply(interpret_elasticity)
    return summary.sort_values("avg_elasticity")


if __name__ == "__main__":
    txn, events = load_data()
    elas = compute_elasticity_table(txn, events)
    elas.to_csv("data/elasticity_events.csv", index=False)
    print(f"Computed elasticity for {len(elas)} price-change events")
    print(elas[["product_name", "change_date", "pct_price_change", "pct_qty_change", "elasticity", "interpretation"]].to_string(index=False))

    summary = product_level_summary(elas)
    summary.to_csv("data/elasticity_by_product.csv", index=False)
    print("\n--- Product-level average elasticity ---")
    print(summary.to_string(index=False))
