"""Generate realistic sample datasets for InsightAI demos.

Creates three CSVs in this directory:
    - sales_data.csv       (transactional sales with dates/regions/categories)
    - customer_data.csv    (customer profiles with churn label)
    - ecommerce_data.csv    (e-commerce orders)

Run with:
    python data/generate_samples.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
RNG = np.random.default_rng(42)


def generate_sales(n: int = 2000) -> pd.DataFrame:
    """Transactional sales dataset with seasonality and regional variation."""
    start = datetime(2023, 1, 1)
    dates = [start + timedelta(days=int(d)) for d in RNG.integers(0, 730, n)]
    regions = RNG.choice(["North", "South", "East", "West", "Central"], n,
                         p=[0.25, 0.2, 0.2, 0.2, 0.15])
    categories = RNG.choice(
        ["Electronics", "Furniture", "Office Supplies", "Apparel", "Groceries"], n,
        p=[0.3, 0.15, 0.2, 0.2, 0.15],
    )
    base_price = {"Electronics": 450, "Furniture": 300, "Office Supplies": 40,
                  "Apparel": 70, "Groceries": 25}
    unit_price = np.array([base_price[c] * RNG.uniform(0.7, 1.4) for c in categories])
    quantity = RNG.integers(1, 12, n)
    revenue = (unit_price * quantity).round(2)
    # East region performs slightly worse over time to create a declining signal.
    discount = RNG.uniform(0, 0.3, n).round(2)
    profit = (revenue * RNG.uniform(0.05, 0.35, n) - revenue * discount * 0.5).round(2)

    df = pd.DataFrame({
        "OrderID": [f"ORD-{100000 + i}" for i in range(n)],
        "Date": dates,
        "Region": regions,
        "Category": categories,
        "UnitPrice": unit_price.round(2),
        "Quantity": quantity,
        "Discount": discount,
        "Revenue": revenue,
        "Profit": profit,
        "CustomerID": RNG.integers(1, 400, n),
    })
    # Inject a little messiness for the cleaning module to find.
    df.loc[RNG.choice(n, 40, replace=False), "Profit"] = np.nan
    df.loc[RNG.choice(n, 15, replace=False), "Region"] = None
    return df.sort_values("Date").reset_index(drop=True)


def generate_customers(n: int = 600) -> pd.DataFrame:
    """Customer profile dataset with a churn target for classification."""
    tenure = RNG.integers(1, 72, n)
    monthly_spend = (RNG.gamma(3, 30, n)).round(2)
    support_tickets = RNG.poisson(2, n)
    satisfaction = RNG.integers(1, 6, n)
    # Churn likelihood rises with tickets/low satisfaction, falls with tenure.
    churn_score = (support_tickets * 0.4 - satisfaction * 0.5 - tenure * 0.02
                   + RNG.normal(0, 0.5, n))
    churn = (churn_score > churn_score.mean()).astype(int)

    df = pd.DataFrame({
        "CustomerID": [f"CUST-{1000 + i}" for i in range(n)],
        "Age": RNG.integers(18, 75, n),
        "Gender": RNG.choice(["Male", "Female"], n),
        "Region": RNG.choice(["North", "South", "East", "West"], n),
        "TenureMonths": tenure,
        "MonthlySpend": monthly_spend,
        "SupportTickets": support_tickets,
        "SatisfactionScore": satisfaction,
        "Churn": churn,
    })
    df.loc[RNG.choice(n, 25, replace=False), "MonthlySpend"] = np.nan
    return df


def generate_ecommerce(n: int = 1500) -> pd.DataFrame:
    """E-commerce orders dataset."""
    start = datetime(2023, 6, 1)
    dates = [start + timedelta(days=int(d)) for d in RNG.integers(0, 365, n)]
    products = RNG.choice(
        ["Laptop", "Phone", "Headphones", "Monitor", "Keyboard", "Webcam", "Chair", "Desk"], n
    )
    price = RNG.uniform(20, 1500, n).round(2)
    qty = RNG.integers(1, 5, n)
    df = pd.DataFrame({
        "TransactionID": [f"TXN-{500000 + i}" for i in range(n)],
        "Date": dates,
        "Product": products,
        "Channel": RNG.choice(["Web", "Mobile App", "Marketplace"], n, p=[0.5, 0.35, 0.15]),
        "Country": RNG.choice(["USA", "UK", "Germany", "India", "Canada"], n),
        "Price": price,
        "Quantity": qty,
        "Sales": (price * qty).round(2),
        "Rating": RNG.integers(1, 6, n),
    })
    return df.sort_values("Date").reset_index(drop=True)


def main() -> None:
    datasets = {
        "sales_data.csv": generate_sales(),
        "customer_data.csv": generate_customers(),
        "ecommerce_data.csv": generate_ecommerce(),
    }
    for name, df in datasets.items():
        path = OUT_DIR / name
        df.to_csv(path, index=False)
        print(f"✓ Wrote {path}  ({df.shape[0]} rows × {df.shape[1]} cols)")


if __name__ == "__main__":
    main()
