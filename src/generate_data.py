"""
generate_data.py
=================
Builds a synthetic but structurally realistic B2B transaction dataset for the
Pricing & Revenue Leakage Command Center.

Every column here is something you would actually find in an ERP/CRM extract
(SAP SD / Salesforce CPQ style): list price, invoice price, and the individual
deduction line items that separate invoice price from pocket price. Nothing
here is model-inferred -- it's generated with explicit business rules so the
downstream waterfall, segmentation, and elasticity calculations have real
"ground truth" arithmetic to work with.

Output: data/transactions.csv  (order-line grain)
        data/price_change_events.csv (product x region price-change log, used for elasticity)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

# ---------------------------------------------------------------------------
# 1. Reference dimensions
# ---------------------------------------------------------------------------

PRODUCTS = [
    {"product_id": "P-1001", "product_name": "Industrial Valve A200", "base_list_price": 4200, "category": "Valves"},
    {"product_id": "P-1002", "product_name": "Industrial Valve A400", "base_list_price": 6800, "category": "Valves"},
    {"product_id": "P-1003", "product_name": "Pressure Sensor S10", "base_list_price": 950, "category": "Sensors"},
    {"product_id": "P-1004", "product_name": "Pressure Sensor S20", "base_list_price": 1450, "category": "Sensors"},
    {"product_id": "P-1005", "product_name": "Hydraulic Pump H100", "base_list_price": 12500, "category": "Pumps"},
    {"product_id": "P-1006", "product_name": "Hydraulic Pump H250", "base_list_price": 21800, "category": "Pumps"},
    {"product_id": "P-1007", "product_name": "Control Module CM3", "base_list_price": 3100, "category": "Controls"},
    {"product_id": "P-1008", "product_name": "Control Module CM5", "base_list_price": 4750, "category": "Controls"},
]

REGIONS = ["North", "South", "East", "West", "Central"]
CHANNELS = ["Direct", "Distributor", "OEM", "E-Commerce"]

# Volume tiers: rule-based, not clustering -- explicit business thresholds
def volume_tier(annual_qty):
    if annual_qty >= 500:
        return "Tier 1 (Strategic, 500+ units/yr)"
    elif annual_qty >= 150:
        return "Tier 2 (Key, 150-499 units/yr)"
    elif annual_qty >= 40:
        return "Tier 3 (Core, 40-149 units/yr)"
    else:
        return "Tier 4 (Long Tail, <40 units/yr)"

N_CUSTOMERS = 260
customers = []
for i in range(N_CUSTOMERS):
    annual_qty = int(np.random.lognormal(mean=4.0, sigma=1.3))
    annual_qty = min(annual_qty, 1400)
    customers.append({
        "customer_id": f"C-{2000+i}",
        "region": np.random.choice(REGIONS, p=[0.24, 0.22, 0.18, 0.20, 0.16]),
        "channel": np.random.choice(CHANNELS, p=[0.35, 0.30, 0.20, 0.15]),
        "annual_qty": annual_qty,
        "tier": volume_tier(annual_qty),
        "payment_terms_days": int(np.random.choice([15, 30, 45, 60, 90], p=[0.1, 0.35, 0.25, 0.2, 0.1])),
    })
cust_df = pd.DataFrame(customers)

# ---------------------------------------------------------------------------
# 2. Transaction-level generation (order line grain)
# ---------------------------------------------------------------------------

start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)
date_range_days = (end_date - start_date).days

# Tier-based base discount rules (rule-based, matches real trade-term grids)
TIER_BASE_DISCOUNT = {
    "Tier 1 (Strategic, 500+ units/yr)": 0.18,
    "Tier 2 (Key, 150-499 units/yr)": 0.12,
    "Tier 3 (Core, 40-149 units/yr)": 0.07,
    "Tier 4 (Long Tail, <40 units/yr)": 0.03,
}
CHANNEL_DISCOUNT_ADDON = {"Direct": 0.00, "Distributor": 0.06, "OEM": 0.09, "E-Commerce": -0.02}

rows = []
line_id = 1

# Track a "current list price" per product that can step up over time (for elasticity events)
price_history = {p["product_id"]: [] for p in PRODUCTS}
current_list_price = {p["product_id"]: p["base_list_price"] for p in PRODUCTS}

# Pre-schedule 1-2 list-price change events per product over the 2-year window
price_change_log = []
for p in PRODUCTS:
    n_changes = np.random.choice([1, 2], p=[0.4, 0.6])
    change_days = sorted(np.random.choice(range(120, date_range_days - 60), size=n_changes, replace=False))
    for cd in change_days:
        change_date = start_date + timedelta(days=int(cd))
        pct_change = np.random.choice([0.03, 0.04, 0.05, 0.06, 0.07, -0.03], p=[0.22, 0.22, 0.2, 0.14, 0.12, 0.10])
        price_change_log.append({
            "product_id": p["product_id"],
            "change_date": change_date,
            "pct_change": pct_change,
        })

price_change_df = pd.DataFrame(price_change_log).sort_values(["product_id", "change_date"]).reset_index(drop=True)

def list_price_on_date(product_id, base_price, order_date):
    changes = price_change_df[(price_change_df.product_id == product_id) & (price_change_df.change_date <= order_date)]
    price = base_price
    for _, ch in changes.iterrows():
        price = price * (1 + ch["pct_change"])
    return round(price, 2)

N_TRANSACTIONS = 9000
for _ in range(N_TRANSACTIONS):
    cust = cust_df.sample(1).iloc[0]
    prod = PRODUCTS[np.random.randint(0, len(PRODUCTS))]
    order_day_offset = np.random.randint(0, date_range_days)
    order_date = start_date + timedelta(days=int(order_day_offset))

    qty = max(1, int(np.random.lognormal(mean=1.8, sigma=1.0)))

    list_price = list_price_on_date(prod["product_id"], prod["base_list_price"], order_date)

    # --- Waterfall deductions (all rule-based, explicit %) ---
    base_disc = TIER_BASE_DISCOUNT[cust["tier"]]
    channel_addon = CHANNEL_DISCOUNT_ADDON[cust["channel"]]
    # small random negotiation noise around the trade-term grid
    negotiation_noise = np.random.normal(0, 0.015)
    invoice_discount_pct = max(0.0, base_disc + channel_addon + negotiation_noise)

    invoice_price = list_price * (1 - invoice_discount_pct)

    # Off-invoice deductions (rebates, freight, payment-term cost) -- these are the
    # "hidden" leakage items that don't show up on the invoice line but erode pocket price
    volume_rebate_pct = 0.02 if cust["tier"].startswith("Tier 1") else (0.012 if cust["tier"].startswith("Tier 2") else 0.0)
    coop_marketing_pct = 0.015 if cust["channel"] in ("Distributor", "OEM") else 0.0
    freight_pct = np.random.uniform(0.008, 0.035)  # varies by region/weight
    payment_terms_cost_pct = (cust["payment_terms_days"] / 365) * 0.10  # cost of capital ~10% annualized

    total_offinvoice_pct = volume_rebate_pct + coop_marketing_pct + freight_pct + payment_terms_cost_pct
    pocket_price = invoice_price * (1 - total_offinvoice_pct)

    rows.append({
        "line_id": f"L-{line_id:06d}",
        "order_date": order_date.date().isoformat(),
        "customer_id": cust["customer_id"],
        "region": cust["region"],
        "channel": cust["channel"],
        "tier": cust["tier"],
        "payment_terms_days": cust["payment_terms_days"],
        "product_id": prod["product_id"],
        "product_name": prod["product_name"],
        "category": prod["category"],
        "qty": qty,
        "list_price": round(list_price, 2),
        "invoice_discount_pct": round(invoice_discount_pct, 4),
        "invoice_price": round(invoice_price, 2),
        "volume_rebate_pct": round(volume_rebate_pct, 4),
        "coop_marketing_pct": round(coop_marketing_pct, 4),
        "freight_pct": round(freight_pct, 4),
        "payment_terms_cost_pct": round(payment_terms_cost_pct, 4),
        "pocket_price": round(pocket_price, 2),
    })
    line_id += 1

df = pd.DataFrame(rows)

# Revenue and $ leakage columns (plain arithmetic, computed once here so the
# dashboard never has to "model" anything -- it just aggregates)
df["list_revenue"] = df["list_price"] * df["qty"]
df["invoice_revenue"] = df["invoice_price"] * df["qty"]
df["pocket_revenue"] = df["pocket_price"] * df["qty"]

df["invoice_discount_leakage"] = df["list_revenue"] - df["invoice_revenue"]
df["volume_rebate_leakage"] = df["invoice_revenue"] * df["volume_rebate_pct"]
df["coop_marketing_leakage"] = df["invoice_revenue"] * df["coop_marketing_pct"]
df["freight_leakage"] = df["invoice_revenue"] * df["freight_pct"]
df["payment_terms_leakage"] = df["invoice_revenue"] * df["payment_terms_cost_pct"]
df["total_leakage"] = df["list_revenue"] - df["pocket_revenue"]

df.to_csv("data/transactions.csv", index=False)
price_change_df.to_csv("data/price_change_events.csv", index=False)
cust_df.to_csv("data/customers.csv", index=False)
pd.DataFrame(PRODUCTS).to_csv("data/products.csv", index=False)

print(f"Generated {len(df):,} transaction lines")
print(f"Total list revenue:   ${df['list_revenue'].sum():,.0f}")
print(f"Total invoice revenue:${df['invoice_revenue'].sum():,.0f}")
print(f"Total pocket revenue: ${df['pocket_revenue'].sum():,.0f}")
print(f"Total leakage:        ${df['total_leakage'].sum():,.0f}  ({df['total_leakage'].sum()/df['list_revenue'].sum():.1%} of list)")
print(f"\nPrice change events logged: {len(price_change_df)}")
print("\nFiles written to data/: transactions.csv, price_change_events.csv, customers.csv, products.csv")
