"""
RewindOS – Reddit Mentions + Engagement Drop-off + "No Backlash" Check
--------------------------------------------------------------------
No-credential version using Reddit public JSON endpoints.

What it does:
- Runs multiple Reddit search queries
- Collects posts metadata (created_utc, score, num_comments, title/selftext)
- Aggregates weekly counts + engagement
- Exports CSV + PNG plots
- Writes debug logs + raw responses + errors.csv

Key deliverable:
- Show that "severance + baby it's cold outside + backlash/problematic/banned" queries return ~0 results.
"""

import os
import re
import time
import json
import math
import hashlib
import traceback
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# CONFIG
# -----------------------------
USER_AGENT = "RewindOSResearchBot/0.1 (by u/yourusername; contact: your@email)"

# Time window: adjust as needed
# If you're aiming to show "after Severance used it", start near the episode date.
START_DATE = "2024-10-01"          # YYYY-MM-DD
END_DATE   = None                  # None = now (UTC)

EVENT_DATE = pd.Timestamp("2025-01-17", tz="UTC")  # Severance S2E7
EVENT_WINDOW_DAYS = 90

# Search scope:
# - set SUBREDDITS = [] to search all Reddit
# - or limit (recommended) to the subs where you’d expect the convo
SUBREDDITS = [
    "severanceappleTVplus",
    "television",
    "appletv",
    "Severance",
    # add more if you want; keep in mind subreddit names are case-insensitive
]

# Query sets (broad vs narrow)
# 1) Broad: does any chatter exist?
QUERY_BROAD = [
    "\"baby it's cold outside\" severance",
    "\"baby it's cold outside\" \"apple tv\"",
    "\"baby its cold outside\" severance",
]

# 2) Backlash/controversy framing: did anyone call it problematic/banned/etc after Severance?
QUERY_BACKLASH = [
    "\"baby it's cold outside\" severance (banned OR cancel OR backlash OR problematic OR sexist)",
    "\"baby it's cold outside\" \"apple tv\" (banned OR cancel OR backlash OR problematic OR sexist)",
    "\"baby its cold outside\" severance (banned OR cancel OR backlash OR problematic OR sexist)",
]

# 3) Your specific phrasing idea
QUERY_SPECIFIC = [
    "\"baby it's cold outside\" banned severance",
    "\"baby it's cold outside\" controversy severance",
]

# Note: Reddit search syntax is not full Boolean; OR sometimes works, sometimes not.
# This script runs multiple variants and logs outcomes.

REQUEST_TIMEOUT = 30
RETRIES = 5
BACKOFF_BASE = 2.0

# Outputs
OUT_DIR = "reddit_outputs"
LOG_FILE = os.path.join(OUT_DIR, "reddit_debug.log")
ERRORS_CSV = os.path.join(OUT_DIR, "reddit_errors.csv")

POSTS_CSV = os.path.join(OUT_DIR, "reddit_posts_raw.csv")
WEEKLY_CSV = os.path.join(OUT_DIR, "reddit_weekly_metrics.csv")
QUERY_SUMMARY_CSV = os.path.join(OUT_DIR, "reddit_query_summary.csv")

PNG_WEEKLY = os.path.join(OUT_DIR, "reddit_weekly_mentions.png")
PNG_ENGAGE = os.path.join(OUT_DIR, "reddit_weekly_engagement.png")
PNG_EVENT  = os.path.join(OUT_DIR, "reddit_event_window.png")

# -----------------------------
# HELPERS
# -----------------------------
_errors = []

def ensure_out_dir():
    os.makedirs(OUT_DIR, exist_ok=True)

def log(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}Z] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def record_error(stage: str, info: dict):
    _errors.append({"stage": stage, **info, "ts_utc": datetime.utcnow().isoformat()})

def flush_errors():
    if not _errors:
        return
    pd.DataFrame(_errors).to_csv(ERRORS_CSV, index=False)
    log(f"Wrote errors CSV: {ERRORS_CSV} ({len(_errors)} rows)")

def safe_filename(prefix: str, content: str, ext: str):
    h = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return os.path.join(OUT_DIR, f"{prefix}_{h}.{ext}")

def to_utc_ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")

def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))

def within_range(created_utc: float, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> bool:
    t = pd.Timestamp(int(created_utc), unit="s", tz="UTC")
    return (t >= start_ts) and (t <= end_ts)

def reddit_search_url(query: str, subreddit: str | None, sort="new", limit=100, after=None):
    # Reddit public JSON endpoint
    base = "https://www.reddit.com"
    if subreddit:
        path = f"/r/{subreddit}/search.json"
    else:
        path = "/search.json"

    params = {
        "q": query,
        "sort": sort,
        "restrict_sr": "1" if subreddit else "0",
        "limit": str(limit),
        "t": "all",
        "type": "link",
    }
    if after:
        params["after"] = after

    return base + path + "?" + urlencode(params)

def request_json(url: str):
    headers = {"User-Agent": USER_AGENT}
    last_exc = None

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            ct = r.headers.get("Content-Type", "")
            log(f"GET {r.status_code} | {ct} | {url[:120]}...")

            if r.status_code in (429, 500, 502, 503, 504):
                record_error("http_retryable", {"status": r.status_code, "url": url[:300], "snippet": r.text[:300]})
                sleep_s = BACKOFF_BASE ** (attempt - 1)
                log(f"Retryable {r.status_code}. Sleeping {sleep_s:.1f}s")
                time.sleep(sleep_s)
                continue

            if r.status_code != 200:
                raw = safe_filename("reddit_raw_http", r.text, "txt")
                with open(raw, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(r.text)
                record_error("http_non_200", {"status": r.status_code, "url": url[:300], "raw_saved_as": raw})
                return None

            try:
                return r.json()
            except Exception as e:
                raw = safe_filename("reddit_raw_parsefail", r.text, "txt")
                with open(raw, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(r.text)
                record_error("json_parse_failed", {"url": url[:300], "raw_saved_as": raw, "exception": repr(e)})
                return None

        except Exception as e:
            last_exc = e
            record_error("request_exception", {"url": url[:300], "exception": repr(e)})
            sleep_s = BACKOFF_BASE ** (attempt - 1)
            time.sleep(sleep_s)

    record_error("request_failed_all_retries", {"url": url[:300], "exception": repr(last_exc)})
    return None

def fetch_posts_for_query(query: str, subreddit: str | None, start_ts: pd.Timestamp, end_ts: pd.Timestamp, max_pages=25):
    """
    Pages through Reddit search results using 'after' token.
    Stops when results fall older than start_ts (best effort).
    """
    posts = []
    after = None
    pages = 0

    while pages < max_pages:
        url = reddit_search_url(query=query, subreddit=subreddit, after=after)
        data = request_json(url)
        if not data or "data" not in data:
            break

        children = data["data"].get("children", [])
        after = data["data"].get("after", None)
        pages += 1

        if not children:
            break

        # Extract
        any_in_range = False
        for child in children:
            try:
                d = child.get("data", {})
                created_utc = d.get("created_utc", None)
                if created_utc is None:
                    continue

                if not within_range(created_utc, start_ts, end_ts):
                    continue

                any_in_range = True
                posts.append({
                    "id": d.get("id"),
                    "fullname": d.get("name"),  # t3_xxx
                    "created_utc": created_utc,
                    "created_dt": pd.Timestamp(int(created_utc), unit="s", tz="UTC"),
                    "subreddit": d.get("subreddit"),
                    "title": d.get("title", ""),
                    "selftext": d.get("selftext", ""),
                    "score": d.get("score", 0),
                    "num_comments": d.get("num_comments", 0),
                    "permalink": "https://www.reddit.com" + d.get("permalink", ""),
                    "query": query,
                    "scope_subreddit": subreddit or "",
                })
            except Exception as e:
                record_error("parse_child_failed", {"exception": repr(e), "query": query, "subreddit": subreddit or ""})

        # If we’re searching sorted "new", once nothing in this page is in range and the window is recent,
        # you can keep paging a bit; but in practice this endpoint isn't strictly ordered for all cases.
        if not after:
            break

        # throttle a bit
        time.sleep(1.0)

    return posts

# -----------------------------
# ANALYSIS + PLOTS
# -----------------------------
def weekly_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["week", "mentions", "score_sum", "comments_sum"])

    d = df.copy()
    d["week"] = d["created_dt"].dt.to_period("W").dt.start_time.dt.tz_localize("UTC")
    agg = d.groupby(["week"]).agg(
        mentions=("id", "nunique"),
        score_sum=("score", "sum"),
        comments_sum=("num_comments", "sum"),
    ).reset_index()
    return agg.sort_values("week")

def plot_weekly(weekly: pd.DataFrame):
    # Mentions
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(weekly["week"], weekly["mentions"])
    ax.axvline(EVENT_DATE, linestyle=":", color="black", label="Severance S2E7")
    ax.set_title("Reddit weekly mentions (all queries combined)")
    ax.set_xlabel("Week")
    ax.set_ylabel("Unique posts")
    ax.legend()
    plt.tight_layout()
    plt.savefig(PNG_WEEKLY, dpi=150)
    plt.close(fig)

    # Engagement
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(weekly["week"], weekly["score_sum"], label="score sum")
    ax.plot(weekly["week"], weekly["comments_sum"], label="comments sum")
    ax.axvline(EVENT_DATE, linestyle=":", color="black", label="Severance S2E7")
    ax.set_title("Reddit weekly engagement (all queries combined)")
    ax.set_xlabel("Week")
    ax.set_ylabel("Engagement")
    ax.legend()
    plt.tight_layout()
    plt.savefig(PNG_ENGAGE, dpi=150)
    plt.close(fig)

def plot_event_window(weekly: pd.DataFrame):
    ws = EVENT_DATE - pd.Timedelta(days=EVENT_WINDOW_DAYS)
    we = EVENT_DATE + pd.Timedelta(days=EVENT_WINDOW_DAYS)
    w = weekly[(weekly["week"] >= ws) & (weekly["week"] <= we)].copy()

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(w["week"], w["mentions"], label="mentions")
    ax.plot(w["week"], w["comments_sum"], label="comments sum")
    ax.axvline(EVENT_DATE, linestyle=":", color="black", label="Severance S2E7")
    ax.set_title(f"Reddit event window (±{EVENT_WINDOW_DAYS} days)")
    ax.set_xlabel("Week")
    ax.set_ylabel("Counts")
    ax.legend()
    plt.tight_layout()
    plt.savefig(PNG_EVENT, dpi=150)
    plt.close(fig)

# -----------------------------
# MAIN
# -----------------------------
def main():
    ensure_out_dir()
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    log("Starting Reddit mention + engagement tracker (no-credential).")

    start_ts = to_utc_ts(START_DATE)
    end_ts = now_utc() if END_DATE is None else to_utc_ts(END_DATE)

    all_queries = []
    for q in QUERY_BROAD:
        all_queries.append(("broad", q))
    for q in QUERY_BACKLASH:
        all_queries.append(("backlash", q))
    for q in QUERY_SPECIFIC:
        all_queries.append(("specific", q))

    all_posts = []
    query_summary = []

    # Search in chosen subreddits (or globally if SUBREDDITS empty)
    scopes = SUBREDDITS if SUBREDDITS else [None]

    for qtype, q in all_queries:
        for sr in scopes:
            log(f"Running query_type={qtype} subreddit={sr or 'ALL'} query={q}")

            posts = fetch_posts_for_query(q, sr, start_ts, end_ts, max_pages=20)
            log(f" -> collected {len(posts)} posts in time window")
            all_posts.extend(posts)

            query_summary.append({
                "query_type": qtype,
                "query": q,
                "subreddit_scope": sr or "ALL",
                "posts_collected": len(posts),
                "start_utc": str(start_ts),
                "end_utc": str(end_ts),
            })

    # Export query summary
    qs_df = pd.DataFrame(query_summary)
    qs_df.to_csv(QUERY_SUMMARY_CSV, index=False)
    log(f"Saved {QUERY_SUMMARY_CSV}")

    # De-duplicate by post id
    df = pd.DataFrame(all_posts)
    if df.empty:
        log("No posts collected across all queries. This may mean true zero OR search limitations.")
        flush_errors()
        # Still write empty outputs for reproducibility
        df.to_csv(POSTS_CSV, index=False)
        pd.DataFrame().to_csv(WEEKLY_CSV, index=False)
        return

    df = df.sort_values("created_dt").drop_duplicates(subset=["id"])
    df.to_csv(POSTS_CSV, index=False)
    log(f"Saved {POSTS_CSV} ({len(df)} unique posts)")

    # Weekly aggregation across all queries combined
    weekly = weekly_aggregate(df)
    weekly.to_csv(WEEKLY_CSV, index=False)
    log(f"Saved {WEEKLY_CSV} ({len(weekly)} weeks)")

    # Plots
    try:
        plot_weekly(weekly)
        log(f"Saved {PNG_WEEKLY} and {PNG_ENGAGE}")
        plot_event_window(weekly)
        log(f"Saved {PNG_EVENT}")
    except Exception as e:
        record_error("plot_failed", {"exception": repr(e), "traceback": traceback.format_exc()[:3000]})

    # Explicit “no backlash” proof table:
    # Count posts from backlash-type queries only
    backlash_posts = df[df["query"].isin(QUERY_BACKLASH)].copy()
    log(f"Backlash-query unique posts: {backlash_posts['id'].nunique()}")

    flush_errors()
    log("Done.")

if __name__ == "__main__":
    main()
