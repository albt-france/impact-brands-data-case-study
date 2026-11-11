"""Collect a dated snapshot of the public product catalogue of each Impact Brands storefront.

PUBLIC DATA. What this script does, step by step:
1. Reads each brand's public sitemap.xml (allowed by every site's robots.txt).
2. Keeps only the product pages (URLs containing /product/).
3. Downloads each product page once, waiting at least 2.5 seconds between requests.
4. Extracts the product data embedded in the page (name, list price, bundle prices,
   subscribe & save prices, store SKU codes found in the add-to-cart links, rating).
5. Saves one raw JSON snapshot per brand: data/raw/storefronts/<brand>/<date>.json

No login, no checkout, no customer reviews text, no personal data.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "storefronts"
DELAY_SECONDS = 2.5
HEADERS = {"User-Agent": "Mozilla/5.0 (independent case study; low-rate catalogue snapshot)"}

# Storefronts verified as part of the group: linked from the group website (theimpactbrands.com)
# and/or showing the same company address in the footer.
BRANDS = {
    "vitalpeak": "https://www.thevitalpeak.com",
    "purehealth_research": "https://www.purehealthresearch.com",
    "nation_health_md": "https://www.nationhealthmd.com",
    "pureance": "https://www.pureance.com",
    "trumeta": "https://www.trumeta.com",
    "petmade": "https://www.petmade.com",
    "natures_blast": "https://www.naturesblaststore.com",
}


def get(session, url):
    """GET with a polite delay after every request."""
    response = session.get(url, headers=HEADERS, timeout=30)
    time.sleep(DELAY_SECONDS)
    return response


def decode_json_after(html, key):
    """Return the JSON value that follows `"key":` in the page, or None."""
    decoder = json.JSONDecoder()
    position = html.find(f'"{key}":')
    if position == -1:
        return None
    start = position + len(key) + 3
    try:
        value, _ = decoder.raw_decode(html[start:])
        return value
    except json.JSONDecodeError:
        return None


def regex_first(pattern, text):
    match = re.search(pattern, text)
    return match.group(1) if match else None


def extract_product(html, url):
    """Pull the embedded product fields out of one product page."""
    # Some pages embed the data inside an escaped JS string: unescape once if needed.
    if '"priceOptions":' not in html and '\\"priceOptions\\":' in html:
        html = html.replace('\\"', '"')

    name = regex_first(r'"@type":\s*"Product",\s*"@id":\s*"[^"]*",\s*"name":\s*"([^"]+)"', html)
    if name is None:
        name = regex_first(r'<title>([^<|]+)', html)
    price_options = decode_json_after(html, "priceOptions")
    regular_price = regex_first(r'"regularPrice":\s*([0-9.]+)', html)
    rating_value = regex_first(r'"ratingValue":\s*"?([0-9.]+)', html)
    rating_count = regex_first(r'"ratingCount":\s*"?([0-9]+)', html)

    return {
        "url": url,
        "name": name.strip() if name else None,
        "regular_price": float(regular_price) if regular_price else None,
        "price_options": price_options,
        "site_rating_value": float(rating_value) if rating_value else None,
        "site_rating_count": int(rating_count) if rating_count else None,
    }


def collect_brand(session, brand, base_url, snapshot_date):
    sitemap = get(session, f"{base_url}/sitemap.xml").text
    product_urls = sorted(set(re.findall(r"<loc>([^<]*/product/[^<]*)</loc>", sitemap)))
    print(f"{brand}: {len(product_urls)} product URLs in sitemap", flush=True)

    products = []
    for url in product_urls:
        try:
            response = get(session, url)
            record = extract_product(response.text, url)
            record["http_status"] = response.status_code
        except requests.RequestException as error:
            record = {"url": url, "http_status": None, "error": str(error)}
        products.append(record)

    snapshot = {
        "brand": brand,
        "base_url": base_url,
        "snapshot_date": snapshot_date,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "sitemap.xml -> /product/ pages -> embedded product JSON",
        "products": products,
    }
    out_file = OUT_DIR / brand / f"{snapshot_date}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False), encoding="utf-8")
    with_prices = sum(1 for p in products if p.get("price_options"))
    print(f"  saved {out_file.relative_to(ROOT)} ({with_prices}/{len(products)} with prices)", flush=True)


def main():
    snapshot_date = date.today().isoformat()
    only = sys.argv[1:]  # optional: collect a subset of brands
    with requests.Session() as session:
        for brand, base_url in BRANDS.items():
            if only and brand not in only:
                continue
            collect_brand(session, brand, base_url, snapshot_date)


if __name__ == "__main__":
    main()
