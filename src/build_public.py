"""Turn the raw public snapshots into clean, analysis-ready CSV tables.

PUBLIC DATA. Inputs: data/raw/storefronts, data/raw/wayback, data/raw/trends.
Outputs (data/public/):
  brands.csv            one row per brand
  catalog_products.csv  one row per product page (dim_product, public part)
  catalog_offers.csv    one row per product x purchase type x bundle size (prices, store SKU codes)
  price_history.csv     archived monthly prices of key products (Wayback Machine)
  product_first_seen.csv first archive capture of each product URL (launch proxy)
  trends_monthly.csv    Google Trends interest, monthly average
The same files are copied into dbt/seeds/public/ so the warehouse can use the real catalogue.
"""
import json
import re
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "public"
SEEDS = ROOT / "dbt" / "seeds" / "public"

BRAND_INFO = {
    # folder name: (brand_code, display name, focus as described on the brand / group sites)
    "purehealth_research": ("PHR", "PureHealth Research", "Doctor-formulated supplements (flagship)"),
    "nation_health_md": ("NHMD", "Nation Health MD", "Doctor-formulated supplements"),
    "pureance": ("PUR", "Pureance", "Skincare and beauty supplements"),
    "trumeta": ("TRU", "Trumeta", "Fitness and sports nutrition"),
    "petmade": ("PET", "PetMade", "Pet wellness"),
    "natures_blast": ("NBL", "Nature's Blast", "Powdered supplements"),
    "vitalpeak": ("VPK", "VitalPeak", "Single-ingredient and value supplements"),
}

# Simple keyword rules: first match wins. Category is a reporting label, not a health claim.
CATEGORY_RULES = [
    ("Gift card", ["gift card", "gift certificate"]),
    ("Pet health", ["dog", "cat ", "pet", "paw"]),
    ("Skin, hair & beauty", ["collagen", "skin", "hair", "serum", "cream", "face", "eye", "beauty",
                             "dermal", "retinol", "glow", "lash", "nail", "toenail", "fungus",
                             "shampoo", "conditioner", "cleansing", "keratin", "roller", "contour"]),
    ("Liver, detox & cleanse", ["liver", "artichoke", "milk thistle", "detox", "cleanse", "kidney", "lymph", "parabroom", "para", "metal"]),
    ("Gut & digestion", ["gut", "biotic", "biome", "enzyme", "gastro", "kombucha", "digest", "colon", "fiber"]),
    ("Metabolism & weight", ["sugar", "metabolic", "weight", "keto", "glp", "switch", "curb", "fit", "berberine",
                             "burn", "greens", "reds", "fat"]),
    ("Brain, mood & sleep", ["brain", "neuro", "nootropic", "cogni", "sleep", "stress", "cortisol", "mood",
                             "focus", "bacopa", "ashwagandha", "memory", "calm"]),
    ("Heart & circulation", ["heart", "beat", "cl balance", "cholesterol", "omega", "vein", "beet", "circulat",
                             "hawthorn", "blood pressure", "garlic"]),
    ("Joint, bone & muscle", ["turmeric", "curcumin", "joint", "bone", "agil", "mobility", "nerve", "muscle", "protein", "creatine"]),
    ("Sports nutrition", ["pre-workout", "preworkout", "electrolyte", "hydration", "bcaa", "whey", "energy"]),
    ("Longevity & vitality", ["longevity", "youth", "nmn", "span", "vital", "ageless", "testo", "tongkat",
                              "exuberant", "shilajit", "men", "prostate", "proflow", "meno", "women",
                              "thyroid"]),
    ("Senses & immunity", ["vision", "hearing", "ear", "immun", "elderberry", "breathe", "oral", "sinus"]),
]


def categorise(name):
    text = f" {name.lower()} "
    for category, keywords in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "General wellness"


def clean_name(name):
    name = (name or "").replace("�", "").replace("®", "").replace("™", "")
    return re.sub(r"\s+", " ", name).strip()


def parse_store_sku(order_link):
    """Store item code + quantity from an add-to-cart link (two URL styles exist)."""
    if not order_link:
        return None, None
    match = re.search(r"ADD_([A-Za-z0-9_-]+)=(\d+)", order_link)
    if match:
        return match.group(1), int(match.group(2))
    match = re.search(r"ADD=([A-Za-z0-9_-]+)", order_link)
    if match:
        quantity = re.search(r"QUANTITY=(\d+)", order_link)   # third style: ADD=CFOF&QUANTITY=3
        return match.group(1), int(quantity.group(1)) if quantity else 1
    return None, None


def offers_from_options(price_options):
    """Flatten priceOptions into one row per purchase type x bundle size."""
    rows = []
    if not isinstance(price_options, dict):
        return rows
    for source_key, purchase_type in (("regular", "one_time"), ("vip", "subscribe_save")):
        options = price_options.get(source_key) or {}
        if not isinstance(options, dict):
            continue
        for size, option in options.items():
            if not isinstance(option, dict) or option.get("price") is None or not str(size).isdigit():
                continue
            size = int(size)
            unit_price = float(option["price"])
            save = float(option.get("save") or 0)
            sku, qty = parse_store_sku(option.get("orderLink"))
            merchant = re.search(r"MerchantID=([A-Za-z0-9]+)", option.get("orderLink") or "")
            rows.append({
                "store_merchant_id": merchant.group(1) if merchant else None,
                "purchase_type": purchase_type,
                "bundle_size": size,
                "unit_price": unit_price,
                "bundle_total": round(unit_price * size, 2),
                "list_unit_price": round(unit_price + save / size, 2),
                "store_sku": sku,
                "store_qty": qty,
            })
    return rows


def load_snapshots():
    products, offers = [], []
    snapshot_dates = {}
    for folder, (code, _, _) in BRAND_INFO.items():
        files = sorted((RAW / "storefronts" / folder).glob("*.json"))
        if not files:
            continue
        snapshot = json.loads(files[-1].read_text(encoding="utf-8"))
        snapshot_dates[code] = snapshot["snapshot_date"]
        for page in snapshot["products"]:
            if page.get("http_status") != 200:
                continue
            slug = page["url"].rstrip("/").split("/")[-1]
            name = clean_name(page.get("name"))
            if name.lower() in ("", "shop", "subscribe"):
                if name.lower() == "subscribe":
                    continue  # a subscription landing page, not a product
                name = slug.replace("-", " ").title()
            page_offers = offers_from_options(page.get("price_options"))
            if not page_offers:
                # Product listed but no price in the page (e.g. sold through offer pages): keep the row.
                products.append({"brand_code": code, "product_slug": slug, "product_name": name,
                                 "category": categorise(name + " " + slug.replace("-", " ")),
                                 "measurement_unit": None, "is_kit_or_bundle": False,
                                 "is_gift_card": False, "list_unit_price": None, "one_time_price_1": None,
                                 "subscribe_price_1": None, "lowest_unit_price": None, "bundle_sizes": None,
                                 "has_subscribe_save": None, "site_rating_value": page.get("site_rating_value"),
                                 "site_rating_count": page.get("site_rating_count"),
                                 "product_url": page["url"], "snapshot_date": snapshot["snapshot_date"],
                                 "price_in_page": False})
                continue
            unit = page["price_options"].get("measurementUnit")
            for offer in page_offers:
                offers.append({"brand_code": code, "product_slug": slug, "product_name": name,
                               "measurement_unit": unit, **offer,
                               "snapshot_date": snapshot["snapshot_date"]})
            one_time = {o["bundle_size"]: o for o in page_offers if o["purchase_type"] == "one_time"}
            subscribe = {o["bundle_size"]: o for o in page_offers if o["purchase_type"] == "subscribe_save"}
            single = one_time.get(1) or (one_time[min(one_time)] if one_time else None)
            single_sub = subscribe.get(1) or (subscribe[min(subscribe)] if subscribe else None)
            all_units = [o["unit_price"] for o in page_offers]
            list_price = max(o["list_unit_price"] for o in page_offers)
            lowered = name.lower()
            products.append({
                "brand_code": code,
                "product_slug": slug,
                "product_name": name,
                "category": categorise(name + " " + slug.replace("-", " ")),
                "measurement_unit": unit,
                "is_kit_or_bundle": bool(unit == "Set" or re.search(r"bundle|protocol|system|kit|stack", lowered)),
                "is_gift_card": "gift card" in lowered,
                "list_unit_price": list_price,
                "one_time_price_1": single["unit_price"] if single else None,
                "subscribe_price_1": single_sub["unit_price"] if single_sub else None,
                "lowest_unit_price": min(all_units),
                "bundle_sizes": "/".join(str(s) for s in sorted(one_time)),
                "has_subscribe_save": bool(subscribe),
                "site_rating_value": page.get("site_rating_value"),
                "site_rating_count": page.get("site_rating_count"),
                "product_url": page["url"],
                "snapshot_date": snapshot["snapshot_date"],
                "price_in_page": True,
            })
    products = pd.DataFrame(products)
    offers = pd.DataFrame(offers)
    # Derived discount metrics (per unit, vs the crossed-out list price)
    products["subscribe_discount_pct"] = (1 - products["subscribe_price_1"] / products["one_time_price_1"]).round(4)
    products["max_discount_vs_list_pct"] = (1 - products["lowest_unit_price"] / products["list_unit_price"]).round(4)
    offers["discount_vs_list_pct"] = (1 - offers["unit_price"] / offers["list_unit_price"]).round(4)
    return products, offers, snapshot_dates


def normalise_product_url(url):
    path = re.sub(r"^https?://", "", url).split("?")[0].split("#")[0].rstrip("/").lower()
    path = path.replace(":80", "").replace("www.", "")
    return path


def load_wayback(products):
    first_seen_files = sorted((RAW / "wayback").glob("product_first_seen_*.json"))
    first_seen = pd.DataFrame()
    if first_seen_files:
        rows = []
        for file in first_seen_files:
            for folder, records in json.loads(file.read_text(encoding="utf-8")).items():
                code = BRAND_INFO[folder][0]
                for record in records:
                    rows.append({"brand_code": code, "url_key": normalise_product_url(record["original"]),
                                 "first_seen": pd.to_datetime(record["timestamp"][:8])})
        first_seen = pd.DataFrame(rows)
        first_seen = first_seen[first_seen["url_key"].str.count("/") == 2]  # domain/product/slug only
        first_seen = first_seen.groupby(["brand_code", "url_key"], as_index=False)["first_seen"].min()
        first_seen["product_slug"] = first_seen["url_key"].str.split("/").str[-1]
        # Several archived URL spellings can point to the same product: keep the earliest capture.
        first_seen = first_seen.groupby(["brand_code", "product_slug"], as_index=False)["first_seen"].min()
        first_seen["in_current_catalogue"] = first_seen.set_index(["brand_code", "product_slug"]).index.isin(
            products.set_index(["brand_code", "product_slug"]).index)

    history = []
    for file in sorted((RAW / "wayback").glob("price_history_*.json")):
        for url, captures in json.loads(file.read_text(encoding="utf-8")).items():
            slug = url.rstrip("/").split("/")[-1]
            for capture in captures:
                for offer in offers_from_options(capture.get("price_options")):
                    history.append({"product_slug": slug, "capture_date": pd.to_datetime(capture["timestamp"][:8]),
                                    **{k: offer[k] for k in ("purchase_type", "bundle_size", "unit_price",
                                                             "list_unit_price")}})
    return first_seen, pd.DataFrame(history)


def load_trends():
    files = sorted((RAW / "trends").glob("trends_us_5y_*.csv"))
    if not files:
        return pd.DataFrame()
    weekly = pd.read_csv(files[-1], parse_dates=["week"]).set_index("week")
    monthly = weekly.resample("MS").mean().round(2)
    monthly.index.name = "month"
    return monthly.reset_index().melt(id_vars="month", var_name="search_term", value_name="interest")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    SEEDS.mkdir(parents=True, exist_ok=True)
    products, offers, snapshot_dates = load_snapshots()
    # The sitemap can list the same product page twice (seen for PHR 'exuberant'): keep one row.
    duplicates = products.duplicated(["brand_code", "product_slug"]).sum()
    products = products.drop_duplicates(["brand_code", "product_slug"]).reset_index(drop=True)
    offers = offers.drop_duplicates(["brand_code", "product_slug", "purchase_type", "bundle_size"])
    print(f"duplicate product pages removed: {duplicates}")
    first_seen, history = load_wayback(products)
    if not first_seen.empty:
        products = products.merge(first_seen[["brand_code", "product_slug", "first_seen"]],
                                  on=["brand_code", "product_slug"], how="left")
        products = products.rename(columns={"first_seen": "first_seen_in_archive"})

    brands = []
    for folder, (code, name, focus) in BRAND_INFO.items():
        sellable = products[(products["brand_code"] == code) & ~products["is_gift_card"]]
        brands.append({
            "brand_code": code,
            "brand_name": name,
            "focus": focus,
            "storefront_folder": folder,
            "catalogue_products": len(sellable),
            "snapshot_date": snapshot_dates.get(code),
        })
    brands = pd.DataFrame(brands)

    products.to_csv(OUT / "catalog_products.csv", index=False)
    offers.to_csv(OUT / "catalog_offers.csv", index=False)
    brands.to_csv(OUT / "brands.csv", index=False)
    if not first_seen.empty:
        first_seen.to_csv(OUT / "product_first_seen.csv", index=False)
    if not history.empty:
        history.to_csv(OUT / "price_history.csv", index=False)
    trends = load_trends()
    if not trends.empty:
        trends.to_csv(OUT / "trends_monthly.csv", index=False)

    for name in ("brands.csv", "catalog_products.csv", "catalog_offers.csv"):
        shutil.copy(OUT / name, SEEDS / f"public_{name}")
    print(brands.to_string(index=False))
    print(f"{len(products)} products, {len(offers)} offers")


if __name__ == "__main__":
    main()
