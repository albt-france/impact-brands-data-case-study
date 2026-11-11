"""Catalogue and price history from the Internet Archive (Wayback Machine).

PUBLIC DATA. Two small, low-rate collections:
A. Product launch proxy: one CDX query per brand lists every archived /product/ URL
   with its FIRST capture date (collapse=urlkey keeps the earliest capture per URL).
B. Price history: for a short list of key products, at most one archived capture per
   month (collapse=timestamp:6), downloaded in raw mode (id_) and parsed with the same
   extractor as the live collector.

Waits at least 2.5 seconds between requests. Output: data/raw/wayback/*.json
"""
import json
import time
from datetime import date
from pathlib import Path

import requests

from collect_storefronts import BRANDS, extract_product

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "wayback"
CDX = "https://web.archive.org/cdx/search/cdx"
DELAY_SECONDS = 2.5
HEADERS = {"User-Agent": "Mozilla/5.0 (independent case study; low-rate archive lookup)"}

# Key products tracked for price history (one or two per brand, picked from the live catalogue).
KEY_PRODUCTS = {
    "purehealth_research": [
        "www.purehealthresearch.com/product/liver-health-formula-supplement",
        "www.purehealthresearch.com/product/lymph-system-support",
        "www.purehealthresearch.com/product/blood-sugar-formula-supplement",
    ],
    "nation_health_md": ["www.nationhealthmd.com/product/activespan-longevity-supplement"],
    "pureance": ["www.pureance.com/product/deepsea-collagen-marine-collagen-supplement"],
    "trumeta": ["www.trumeta.com/product/metabolic-reds"],
    "petmade": ["www.petmade.com/product/hip-and-joint-formula"],
    "natures_blast": ["www.naturesblaststore.com/product/liver-360-liver-health-supplement"],
}


def get(session, url, params=None):
    for attempt in range(3):
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=90)
            time.sleep(DELAY_SECONDS)
            if response.status_code == 200:
                return response
        except requests.RequestException:
            time.sleep(10)
    return None


def first_seen_product_urls(session, domain):
    """A. Earliest archive capture of every /product/ URL of one domain."""
    params = {
        "url": f"{domain}/product/",
        "matchType": "prefix",
        "output": "json",
        "fl": "original,timestamp,statuscode",
        "filter": "statuscode:200",
        "collapse": "urlkey",
    }
    response = get(session, CDX, params)
    if response is None or not response.text.strip():
        return []
    rows = response.json()
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def monthly_price_history(session, url):
    """B. One capture per month since 2023, parsed for prices."""
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "from": "2023",
        "collapse": "timestamp:6",
    }
    response = get(session, CDX, params)
    if response is None or not response.text.strip():
        return []
    rows = response.json()[1:]
    history = []
    for timestamp, original, _ in rows:
        page = get(session, f"https://web.archive.org/web/{timestamp}id_/{original}")
        if page is None:
            history.append({"timestamp": timestamp, "error": "fetch failed"})
            continue
        record = extract_product(page.text, original)
        record["timestamp"] = timestamp
        history.append(record)
    return history


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    with requests.Session() as session:
        launches = {}
        for brand, base_url in BRANDS.items():
            domain = base_url.replace("https://", "")
            launches[brand] = first_seen_product_urls(session, domain)
            print(f"{brand}: {len(launches[brand])} archived product URLs", flush=True)
        (OUT_DIR / f"product_first_seen_{today}.json").write_text(
            json.dumps(launches, indent=1), encoding="utf-8")

        prices = {}
        for brand, urls in KEY_PRODUCTS.items():
            for url in urls:
                prices[url] = monthly_price_history(session, url)
                ok = sum(1 for r in prices[url] if r.get("price_options"))
                print(f"{url}: {ok}/{len(prices[url])} monthly captures parsed", flush=True)
        (OUT_DIR / f"price_history_{today}.json").write_text(
            json.dumps(prices, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
