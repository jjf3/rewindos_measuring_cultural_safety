"""
RewindOS – Google Trends Controversy Decay Analysis (CSV Export)
---------------------------------------------------------------
Exports:
1. Full smoothed trends
2. Metric summary (slope + half-life)
3. Event window extract around Severance S2E7
"""

from pytrends.request import TrendReq
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt

# -----------------------------
# CONFIG
# -----------------------------
START_DATE = "2018-01-01"
END_DATE   = "2025-03-31"
GEO        = "US"
SMOOTH_WEEKS = 4

EVENT_DATE = pd.Timestamp("2025-01-17")  # Severance S2E7
EVENT_WINDOW_DAYS = 60

CONTROVERSY_TERMS = [
    "baby it's cold outside controversy",
    "baby its cold outside banned",
    "baby its cold outside problematic"
]

CONTROL_TERMS = [
    "white christmas song"
]

# Output files
RAW_EXPORT      = "google_trends_raw_smoothed.csv"
METRICS_EXPORT  = "google_trends_metrics_summary.csv"
EVENT_EXPORT    = "google_trends_event_window.csv"

# -----------------------------
# FUNCTIONS
# -----------------------------
def fetch_trends(keywords):
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(
        keywords,
        timeframe=f"{START_DATE} {END_DATE}",
        geo=GEO
    )
    df = pytrends.interest_over_time()
    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])
    return df.reset_index()

def smooth(df):
    for col in df.columns:
        if col != "date":
            df[col] = df[col].rolling(SMOOTH_WEEKS, min_periods=1).mean()
    return df

def compute_slope(df, col, start_year=2020):
    subset = df[df["date"] >= pd.Timestamp(f"{start_year}-01-01")].copy()
    subset["t"] = (subset["date"] - subset["date"].min()).dt.days
    X = subset[["t"]].values
    y = subset[col].values
    model = LinearRegression().fit(X, y)
    return model.coef_[0] * 365  # per year

def compute_half_life(df, col):
    peak_idx = df[col].idxmax()
    peak_date = df.loc[peak_idx, "date"]
    peak_val = df.loc[peak_idx, col]
    half_val = peak_val / 2

    after_peak = df[df["date"] >= peak_date]
    half_row = after_peak[after_peak[col] <= half_val]

    if half_row.empty:
        return None

    half_date = half_row.iloc[0]["date"]
    return round((half_date - peak_date).days / 7, 2)  # weeks

# -----------------------------
# FETCH + PREP
# -----------------------------
print("Fetching Google Trends data...")
controversy_df = fetch_trends(CONTROVERSY_TERMS)
control_df     = fetch_trends(CONTROL_TERMS)

controversy_df = smooth(controversy_df)
control_df     = smooth(control_df)

# Merge for export
full_df = pd.merge(
    controversy_df,
    control_df,
    on="date",
    how="left"
)

# -----------------------------
# METRICS SUMMARY
# -----------------------------
rows = []

for term in CONTROVERSY_TERMS:
    rows.append({
        "term": term,
        "type": "controversy",
        "slope_index_per_year": round(compute_slope(full_df, term), 4),
        "outrage_half_life_weeks": compute_half_life(full_df, term)
    })

control_term = CONTROL_TERMS[0]
rows.append({
    "term": control_term,
    "type": "control",
    "slope_index_per_year": round(compute_slope(full_df, control_term), 4),
    "outrage_half_life_weeks": None
})

metrics_df = pd.DataFrame(rows)

# -----------------------------
# EVENT WINDOW EXTRACT
# -----------------------------
event_df = full_df[
    (full_df["date"] >= EVENT_DATE - pd.Timedelta(days=EVENT_WINDOW_DAYS)) &
    (full_df["date"] <= EVENT_DATE + pd.Timedelta(days=EVENT_WINDOW_DAYS))
].copy()

event_df["event_day_offset"] = (event_df["date"] - EVENT_DATE).dt.days

# -----------------------------
# EXPORT CSVs
# -----------------------------
full_df.to_csv(RAW_EXPORT, index=False)
metrics_df.to_csv(METRICS_EXPORT, index=False)
event_df.to_csv(EVENT_EXPORT, index=False)

print("\nExports complete:")
print(f" - {RAW_EXPORT}")
print(f" - {METRICS_EXPORT}")
print(f" - {EVENT_EXPORT}")

# -----------------------------
# OPTIONAL PLOT
# -----------------------------
plt.figure(figsize=(14, 7))

for term in CONTROVERSY_TERMS:
    plt.plot(full_df["date"], full_df[term], label=term)

plt.plot(
    full_df["date"],
    full_df[control_term],
    linestyle="--",
    alpha=0.6,
    label="control: white christmas song"
)

plt.axvline(EVENT_DATE, color="black", linestyle=":", label="Severance S2E7")

plt.title("Google Trends – Controversy Decay vs Control (US)")
plt.ylabel("Search Interest (normalized)")
plt.xlabel("Date")
plt.legend()
plt.tight_layout()
plt.show()
