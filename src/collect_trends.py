"""Relative search interest per brand from Google Trends (United States, last 5 years).

PUBLIC DATA. Uses the pytrends library (unofficial client of the public Trends endpoints).
Google Trends compares at most 5 terms per request and rescales every request to 0-100,
so the brands are split into two batches that share one anchor term (PureHealth Research).
The second batch is then rescaled onto the first through that shared anchor.
Output: data/raw/trends/trends_us_5y_<date>.csv
"""
import time
from datetime import date
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "trends"
ANCHOR = "PureHealth Research"
BATCHES = [
    [ANCHOR, "Nation Health MD", "Pureance", "Trumeta"],
    [ANCHOR, "PetMade", "Nature's Blast", "VitalPeak"],
]


def fetch(pytrends, terms):
    pytrends.build_payload(terms, timeframe="today 5-y", geo="US")
    frame = pytrends.interest_over_time()
    time.sleep(10)  # stay far below any rate limit
    return frame.drop(columns=["isPartial"], errors="ignore")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pytrends = TrendReq(hl="en-US", tz=0)
    first = fetch(pytrends, BATCHES[0])
    second = fetch(pytrends, BATCHES[1])

    # Rescale batch 2 so that the anchor has the same total in both batches.
    factor = first[ANCHOR].sum() / max(second[ANCHOR].sum(), 1)
    second_scaled = second.drop(columns=[ANCHOR]) * factor

    combined = first.join(second_scaled)
    combined.index.name = "week"
    out_file = OUT_DIR / f"trends_us_5y_{date.today().isoformat()}.csv"
    combined.round(2).to_csv(out_file)
    print(f"saved {out_file} ({len(combined)} weeks), anchor rescale factor {factor:.3f}")


if __name__ == "__main__":
    main()
