# Pricing & Revenue Leakage Command Center

A B2B pricing analytics project built entirely on transparent, reproducible arithmetic — no clustering, no regression, no black-box models anywhere in the pipeline.

## What this is

A price-waterfall and revenue-leakage diagnostic for a B2B industrial products business (valves, sensors, pumps, control modules), covering:

1. **Price Waterfall** — List Price → Invoice Price → Pocket Price, with a full leakage bridge across discounts, rebates, co-op/marketing, freight, and payment-term cost of capital.
2. **Rule-Based Segmentation** — Customers segmented by explicit thresholds: volume tier (annual quantity bands) × channel × geography. No clustering algorithm is used.
3. **Price Elasticity** — Classic arc elasticity (`%Δ Quantity ÷ %Δ Price`) computed from 45-day pre/post windows around 12 real logged price-change events in the data. No regression is fit.
4. **Scenario Planner** — "Raise price X% for Segment Y → margin impact" tables, built with plain arithmetic informed by the observed elasticity.
5. **Interactive Dashboard** — Streamlit + Plotly app with filters, waterfall charts, segment tables, elasticity detail, and a live scenario slider.
6. **Executive Summary** — One-page business-readable summary (`reports/executive_summary.md`).

Every number on the dashboard traces back to a `SUM`, `GROUPBY`, or `%Δ/%Δ` calculation on the transaction table — nothing is inferred by a model.

## Project structure

```
pricing-leakage-cc/
├── data/
│   ├── transactions.csv          # 9,000 order-line transactions (2024–2025)
│   ├── customers.csv             # 260 customers with tier/channel/region/terms
│   ├── products.csv              # 8 SKUs across 4 categories
│   ├── price_change_events.csv   # 12 logged list-price change events
│   ├── elasticity_events.csv     # computed elasticity per event
│   ├── elasticity_by_product.csv # product-level average elasticity
│   ├── waterfall_bridge.csv      # aggregate waterfall bridge
│   ├── leakage_breakdown.csv     # leakage $ by component
│   ├── segment_summary.csv       # tier × channel × region rollup
│   └── scenario_*.csv            # pre-computed scenario tables (+5%, -5%, +10%)
├── src/
│   ├── generate_data.py          # synthetic but rule-based transaction generator
│   ├── waterfall.py              # waterfall bridge + segmentation calculations
│   ├── elasticity.py             # event-based elasticity calculator
│   └── scenario.py               # price-change → margin-impact scenario engine
├── dashboard/
│   └── app.py                    # Streamlit dashboard (4 tabs)
├── reports/
│   └── executive_summary.md      # one-page business summary
├── requirements.txt
└── README.md
```

## How to run

### 1. Set up environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. (Optional) Regenerate the data
The CSVs in `data/` are already generated and committed. To regenerate from scratch:
```bash
cd src
python generate_data.py
python waterfall.py
python elasticity.py
python scenario.py
```

### 3. Launch the dashboard
```bash
streamlit run dashboard/app.py
```
Opens at `http://localhost:8501`.

## Method notes (what's calculated, not modeled)

| Component | Method | Not used |
|---|---|---|
| Price Waterfall | `SUM()` of pre-computed $ deduction columns, aggregated by any filter combination | No forecasting |
| Segmentation | Fixed rule thresholds: Tier 1 ≥500 units/yr, Tier 2 150–499, Tier 3 40–149, Tier 4 <40, crossed with channel and region | No k-means / clustering |
| Elasticity | `(%Δ avg daily qty) / (%Δ price)` around each of 12 real price-change events, using 45-day pre/post windows | No OLS / log-log regression fit |
| Scenario table | `new_qty = qty × (1 + elasticity × %Δprice)`; `margin_impact = new_pocket_revenue − current_pocket_revenue` | No optimization solver |

## Business framing

This mirrors the classic McKinsey / Simon-Kucher "pocket price waterfall" used in commercial excellence and pricing engagements — the goal is to make ~14% of list revenue that is currently leaking through discounts, rebates, freight, and payment terms visible and actionable at the segment level, then quantify the margin trade-off of closing part of that gap through price action.

## Author

Shikhar Yadav — B.Tech Production & Industrial Engineering, DTU (2027)
GitHub: [Shikhar-ydv24](https://github.com/Shikhar-ydv24)
