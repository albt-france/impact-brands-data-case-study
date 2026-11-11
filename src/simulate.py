"""Generate SIMULATED internal data for a D2C health & wellness group, on top of the REAL public catalogue.

Everything written by this script is SIMULATED. It is not Impact Brands data.
It imitates the raw tables a data team typically receives from its source systems:

  raw_shop_orders, raw_shop_order_lines   storefront (orders in store local time, store SKU codes)
  raw_subscriptions, raw_subscription_events   subscription tool (current state + event history)
  raw_payments                            payment provider (UTC epoch seconds, amounts in cents)
  raw_fulfillment                         3PL / warehouse (its own SKU codes)
  raw_meta_ads, raw_google_ads            ad platform connectors (account time zone + currency)
  raw_ad_billing                          monthly invoices from the ad platforms (external reference)
  raw_crm_customers                       e-mail / CRM contacts (hashed e-mails only)
  raw_finance_month_close                 net revenue per month as booked by Finance at month close

It also writes the versioned mapping seeds for dbt and a hidden answer key
(data/simulated/seed_injected_issues.csv) listing every problem injected on purpose,
so that we can measure how many of them the dbt tests actually catch.

The real catalogue (products, bundle sizes, prices, subscribe & save prices, store SKU codes)
comes from data/public/catalog_offers.csv (PUBLIC DATA, see data/SOURCES.md).
All assumptions are listed in data/ASSUMPTIONS.md. Fixed seed: 42.
"""
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"
OUT = ROOT / "data" / "simulated"
SEEDS = ROOT / "dbt" / "seeds"

START = pd.Timestamp("2025-01-01")
END = pd.Timestamp("2026-09-30")          # last simulated day (store local time)
DAYS = pd.date_range(START, END, freq="D")
STORE_TZ = "America/New_York"
UTC = ZoneInfo("UTC")

# Share of the group's activity per brand (assumption, flagship-heavy portfolio)
BRAND_WEIGHT = {"PHR": 0.46, "NHMD": 0.15, "PUR": 0.10, "NBL": 0.09, "VPK": 0.07, "TRU": 0.07, "PET": 0.06}
BRAND_NAME = {"PHR": "PureHealth Research", "NHMD": "Nation Health MD", "PUR": "Pureance", "TRU": "Trumeta",
              "PET": "PetMade", "NBL": "Nature's Blast", "VPK": "VitalPeak"}
# First word(s) a campaign name can start with, per brand (used by the brand consistency test)
BRAND_TOKENS = {"PHR": ["phr", "purehealth"], "NHMD": ["nhmd", "nation"], "PUR": ["pur", "pureance"],
                "TRU": ["tru", "trumeta"], "PET": ["pet", "petmade"], "NBL": ["nbl", "nature"],
                "VPK": ["vpk", "vitalpeak"]}
COUNTRIES = [("US", "USD", 0.86), ("CA", "USD", 0.04), ("GB", "GBP", 0.04), ("IE", "EUR", 0.02),
             ("DE", "EUR", 0.02), ("FR", "EUR", 0.02)]
# Approximate monthly FX rates (USD per 1 unit of currency), rounded. Used only to convert simulated amounts.
FX = {"EUR": [1.04, 1.04, 1.08, 1.12, 1.13, 1.15, 1.17, 1.16, 1.17, 1.16, 1.15, 1.17,
              1.17, 1.17, 1.16, 1.15, 1.16, 1.17, 1.16, 1.16, 1.17, 1.16, 1.16],
      "GBP": [1.24, 1.25, 1.29, 1.31, 1.33, 1.35, 1.36, 1.34, 1.35, 1.33, 1.31, 1.33,
              1.34, 1.35, 1.34, 1.33, 1.34, 1.35, 1.34, 1.33, 1.34, 1.33, 1.33]}
FX_MONTHS = pd.period_range("2025-01", "2026-11", freq="M")

GENERIC_WORDS = {"formula", "supplement", "supplements", "support", "complex", "extract", "the", "and", "for",
                 "with", "plus", "a", "of"}

# Injected issue settings
NEW_ACCOUNT_START = pd.Timestamp("2026-05-04")      # issue 1: new Meta account (VitalPeak)
CONNECTOR_PICKUP = pd.Timestamp("2026-05-09")       # ...connector only syncs it from this day
NEW_PRODUCT_LAUNCH = pd.Timestamp("2026-07-01")     # issue 2: new product without mapping
DUPLICATE_LOAD_DAY = pd.Timestamp("2026-05-14")     # issue 5: connector loads one day twice
CHARGEBACK_WAVE_MONTH = "2026-03"                   # issue 6: dispute wave hits a closed month
CENTS_BUG_BATCH = "manual_import_2026_04"           # issue 8: amounts imported in units, not cents


# ---------------------------------------------------------------- helpers
def product_words(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    core = [w for w in words if w not in GENERIC_WORDS]
    return core or words


def product_token(name):
    """Squashed core name used by the campaign rules: 'Blood Sugar Formula' -> 'bloodsugar'."""
    return "".join(product_words(name))


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def fx_rate(currency, day):
    if currency == "USD":
        return 1.0
    return FX[currency][FX_MONTHS.get_loc(pd.Period(day, freq="M"))]


def seasonality(day):
    """Demand index: January resolutions, Q4 peak, summer dip (assumption)."""
    month_factor = {1: 1.15, 2: 1.0, 3: 1.0, 4: 0.97, 5: 0.95, 6: 0.88, 7: 0.85, 8: 0.9,
                    9: 0.97, 10: 1.02, 11: 1.18, 12: 1.08}[day.month]
    weekday_factor = [1.05, 1.03, 1.0, 1.0, 0.97, 0.95, 1.0][day.weekday()]
    growth = 1 + 0.25 * (day - START).days / 365   # +25% a year
    return month_factor * weekday_factor * growth


def local_to_utc(local_ts, tz=STORE_TZ):
    return local_ts.tz_localize(tz, ambiguous=False, nonexistent="shift_forward").tz_convert("UTC").tz_localize(None)


def fmt(ts):
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- catalogue (PUBLIC DATA)
def load_catalogue():
    products = pd.read_csv(PUBLIC / "catalog_products.csv")
    offers = pd.read_csv(PUBLIC / "catalog_offers.csv")
    offers["price_source"] = "public catalogue"
    # VitalPeak pages show no price: ASSUMED price ladder = the group's single-ingredient tier
    # (39 / 35 / 32 one-time, 10% less on subscribe & save) and invented store codes.
    no_price = products[products["one_time_price_1"].isna() & ~products["is_gift_card"]]
    assumed = []
    for _, product in no_price.iterrows():
        initials = "".join(w[0] for w in product_words(product["product_name"])).upper()[:4]
        for purchase_type, ladder, suffix in (("one_time", (39, 35, 32), ""), ("subscribe_save", (35.1, 31.5, 28.8), "AD")):
            for size, price in zip((1, 3, 6), ladder):
                assumed.append({"brand_code": product["brand_code"], "product_slug": product["product_slug"],
                                "product_name": product["product_name"], "store_merchant_id": "VPK",
                                "purchase_type": purchase_type, "bundle_size": size, "unit_price": price,
                                "bundle_total": round(price * size, 2), "list_unit_price": 49.0,
                                "store_sku": f"VP{initials}{size}{suffix}", "store_qty": 1,
                                "price_source": "assumed (no price in page)"})
        products.loc[product.name, "one_time_price_1"] = 39
    offers = pd.concat([offers, pd.DataFrame(assumed)], ignore_index=True)
    products = products[~products["is_gift_card"] & products["one_time_price_1"].notna()].copy()
    products["product_key"] = products["brand_code"] + ":" + products["product_slug"]
    offers["product_key"] = offers["brand_code"] + ":" + offers["product_slug"]
    offers = offers[offers["product_key"].isin(products["product_key"])]
    # Popularity proxy: number of on-site reviews (real), damped. Kits sell less.
    popularity = (products["site_rating_count"].fillna(2) + 5) ** 0.75
    popularity = popularity * np.where(products["is_kit_or_bundle"], 0.3, 1.0)
    products["popularity"] = popularity
    products["token"] = products["product_name"].map(product_token)
    return products.reset_index(drop=True), offers.reset_index(drop=True)


def pick_new_product(products):
    """Issue 2: the most recently archived product of the flagship brand plays the 'new launch'."""
    phr = products[products["brand_code"] == "PHR"].copy()
    if "first_seen_in_archive" in phr and phr["first_seen_in_archive"].notna().any():
        phr = phr.sort_values("first_seen_in_archive", ascending=False, na_position="last")
    else:
        phr = phr.sort_values("popularity")
    return phr.iloc[0]["product_key"]


# ---------------------------------------------------------------- mapping seeds (versioned)
def build_mapping_seeds(products, offers, new_product_key):
    """Initial mapping bootstrapped from the real catalogue; fix rows get fixed_in_version = 1."""
    rows = []
    # Shop SKUs: the real codes from the add-to-cart links (two code styles exist)
    for _, offer in offers.drop_duplicates(["store_sku"]).iterrows():
        if pd.isna(offer["store_sku"]):
            continue
        units = int(offer["bundle_size"]) if offer["store_qty"] == 1 and offer["bundle_size"] > 1 else 1
        rows.append({"source_system": "shop", "source_sku": offer["store_sku"],
                     "product_key": offer["product_key"], "units_per_item": units,
                     "purchase_type": offer["purchase_type"],
                     "fixed_in_version": 1 if offer["product_key"] == new_product_key else 0,
                     "note": "new product launched without mapping - added after alert"
                     if offer["product_key"] == new_product_key else "bootstrapped from public catalogue"})
    # Warehouse SKUs: the 3PL uses its own codes (one code per bottle/jar)
    for i, product in products.reset_index(drop=True).iterrows():
        rows.append({"source_system": "warehouse", "source_sku": f"WH-{product['brand_code']}-{10000 + i * 7}",
                     "product_key": product["product_key"], "units_per_item": 1, "purchase_type": "any",
                     "fixed_in_version": 1 if product["product_key"] == new_product_key else 0,
                     "note": "3PL item master"})
    mapping = pd.DataFrame(rows)
    mapping["source_sku"] = mapping["source_sku"].astype(str)
    return mapping


def build_campaign_rules(products):
    rules = []
    for _, product in products.iterrows():
        rules.append({"brand_code": product["brand_code"], "match_token": product["token"],
                      "campaign_id": None, "product_key": product["product_key"],
                      "fixed_in_version": 0, "note": "core product name"})
    return pd.DataFrame(rules).drop_duplicates(["brand_code", "match_token"]).reset_index(drop=True)


# ---------------------------------------------------------------- ad accounts and campaigns
def build_accounts():
    accounts = []
    counter = 0
    for brand in BRAND_WEIGHT:
        counter += 1
        accounts.append({"platform": "meta", "account_id": f"act_{1011223344550 + counter * 7919}",
                         "account_name": f"{BRAND_NAME[brand]} - US", "brand_code": brand,
                         "account_timezone": "America/New_York", "currency": "USD", "start_date": START})
        accounts.append({"platform": "google", "account_id": f"{300 + counter}-{410 + counter * 3}-{5600 + counter * 11}",
                         "account_name": f"{BRAND_NAME[brand]} Search", "brand_code": brand,
                         "account_timezone": "America/Los_Angeles", "currency": "USD", "start_date": START})
    # International Meta account for the flagship, billed in EUR, Vilnius time
    accounts.append({"platform": "meta", "account_id": "act_1011223399001", "account_name": "PureHealth Research - EU/UK",
                     "brand_code": "PHR", "account_timezone": "Europe/Vilnius", "currency": "EUR",
                     "start_date": pd.Timestamp("2025-03-01")})
    # Issue 1: new VitalPeak Meta account, opened 2026-05-04
    accounts.append({"platform": "meta", "account_id": "act_1011223399777", "account_name": "VitalPeak - US 2",
                     "brand_code": "VPK", "account_timezone": "America/New_York", "currency": "USD",
                     "start_date": NEW_ACCOUNT_START})
    return pd.DataFrame(accounts)


def campaign_name(style, brand, product_name, version):
    words = product_words(product_name)
    camel = "".join(w.capitalize() for w in words)
    if style == 0:
        return f"{brand}_{camel}_US_v{version}"
    if style == 1:
        return f"{brand.lower()}-{'-'.join(words)}-us"
    if style == 2:
        return f"{BRAND_NAME[brand]} | {product_name} | Prospecting | US"
    return f"[{brand}] {' '.join(words)} - retargeting - broad"


def build_campaigns(accounts, products, new_product_key):
    campaigns, issues = [], []
    next_id = {"meta": 23851000000000, "google": 17840000000}
    for _, account in accounts.iterrows():
        brand_products = products[products["brand_code"] == account["brand_code"]]
        heroes = brand_products.sort_values("popularity", ascending=False).head(6 if account["platform"] == "meta" else 4)
        for rank, (_, product) in enumerate(heroes.iterrows()):
            if product["product_key"] == new_product_key:
                continue
            next_id[account["platform"]] += 1 + int(rng.integers(1, 50))
            campaigns.append({"campaign_id": str(next_id[account["platform"]]), "account_id": account["account_id"],
                              "platform": account["platform"], "brand_code": account["brand_code"],
                              "product_key": product["product_key"],
                              "campaign_name": campaign_name(int(rng.integers(0, 4)), account["brand_code"],
                                                             product["product_name"], int(rng.integers(1, 5))),
                              "budget_weight": product["popularity"] / heroes["popularity"].sum(),
                              "start": max(account["start_date"], START), "end": END})
    campaigns = pd.DataFrame(campaigns)

    def add_campaign(account_id, product_key, name, start, issue_type, description, detect=True):
        account = accounts.set_index("account_id").loc[account_id]
        next_id[account["platform"]] += 97
        cid = str(next_id[account["platform"]])
        campaigns.loc[len(campaigns)] = {"campaign_id": cid, "account_id": account_id, "platform": account["platform"],
                                         "brand_code": account["brand_code"], "product_key": product_key,
                                         "campaign_name": name, "budget_weight": 0.35, "start": start, "end": END}
        issues.append({"issue_type": issue_type, "description": description, "detect_key": cid if detect else cid})
        return cid

    by_key = products.set_index("product_key")
    phr_meta = accounts[(accounts.brand_code == "PHR") & (accounts.platform == "meta") & (accounts.currency == "USD")].iloc[0]
    pur_meta = accounts[(accounts.brand_code == "PUR") & (accounts.platform == "meta")].iloc[0]
    vpk_new = accounts[accounts.account_id == "act_1011223399777"].iloc[0]

    # Issue 3a: misspelled product in the campaign name
    sugar = products[(products.brand_code == "PHR") & products.token.str.contains("bloodsugar")]
    if not sugar.empty:
        add_campaign(phr_meta.account_id, sugar.iloc[0].product_key, "PHR_BloodSugr_US_v4",
                     pd.Timestamp("2026-02-02"), 3, "Misspelled product in campaign name (BloodSugr)")
    # Issue 3b: wrong brand prefix in the name (Pureance campaign named PHR_...)
    pur_hero = products[products.brand_code == "PUR"].sort_values("popularity").iloc[-1]
    add_campaign(pur_meta.account_id, pur_hero.product_key,
                 f"PHR_{''.join(w.capitalize() for w in product_words(pur_hero.product_name))}_US_v1",
                 pd.Timestamp("2026-03-10"), 3, "Wrong brand prefix in campaign name (PHR on a Pureance account)")
    # Issue 3c: name matches the wrong product -> silently mis-attributed (no test is designed for it)
    sleep = products[(products.brand_code == "PHR") & (products.token == "sleep")]
    stress = products[(products.brand_code == "PHR") & products.token.str.startswith("stress")]
    if not sleep.empty and not stress.empty:
        add_campaign(phr_meta.account_id, stress.iloc[0].product_key, "PHR_Sleep_StressRelief_Bundle_US",
                     pd.Timestamp("2026-04-06"), 3,
                     "Campaign for Stress Release Complex named 'Sleep_StressRelief': matches the Sleep Formula rule")
    # Issue 1: campaigns of the new VitalPeak account
    vpk_heroes = products[products.brand_code == "VPK"].sort_values("popularity", ascending=False).head(2)
    for _, product in vpk_heroes.iterrows():
        next_id["meta"] += 131
        campaigns.loc[len(campaigns)] = {"campaign_id": str(next_id["meta"]), "account_id": vpk_new.account_id,
                                         "platform": "meta", "brand_code": "VPK", "product_key": product.product_key,
                                         "campaign_name": campaign_name(0, "VPK", product.product_name, 1),
                                         "budget_weight": 0.8, "start": NEW_ACCOUNT_START, "end": END}
    # Issue 2: the new product gets its own campaign from launch day
    new_product = by_key.loc[new_product_key]
    next_id["meta"] += 177
    campaigns.loc[len(campaigns)] = {"campaign_id": str(next_id["meta"]), "account_id": phr_meta.account_id,
                                     "platform": "meta", "brand_code": "PHR", "product_key": new_product_key,
                                     "campaign_name": campaign_name(0, "PHR", new_product.product_name, 1),
                                     "budget_weight": 0.6, "start": NEW_PRODUCT_LAUNCH, "end": END}
    return campaigns, issues


# ---------------------------------------------------------------- daily ad delivery
def simulate_ads(accounts, campaigns):
    """Daily spend per campaign (USD), with the true number of paid orders it drives."""
    total_daily_budget = 4500.0     # USD per day across the group at the start (assumption, scaled down)
    rows = []
    acc = accounts.set_index("account_id")
    brand_cpa = {b: float(rng.uniform(55, 80)) for b in BRAND_WEIGHT}
    platform_share = {"meta": 0.68, "google": 0.32}
    for _, c in campaigns.iterrows():
        account = acc.loc[c.account_id]
        n_in_account = (campaigns.account_id == c.account_id).sum()
        base = total_daily_budget * BRAND_WEIGHT[c.brand_code] * platform_share[c.platform]
        if account.currency == "EUR":
            base *= 0.15
        weight = c.budget_weight if n_in_account > 1 else 1.0
        cpa = brand_cpa[c.brand_code] * float(rng.uniform(0.85, 1.2)) * (1.1 if c.platform == "meta" else 0.9)
        days = DAYS[(DAYS >= c.start) & (DAYS <= c.end)]
        noise = rng.lognormal(0, 0.22, len(days))
        for day, eps in zip(days, noise):
            spend_usd = base * weight * seasonality(day) * eps
            true_orders = rng.poisson(spend_usd / cpa)
            rows.append({"date": day, "campaign_id": c.campaign_id, "account_id": c.account_id,
                         "spend_usd": round(spend_usd, 2), "true_orders": int(true_orders)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- orders, subscriptions, payments
class Ids:
    def __init__(self):
        self.order = 1_000_000
        self.payment = 0
        self.subscription = 500_000
        self.event = 0
        self.customer = 0
        self.shipment = 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (SEEDS / "mapping").mkdir(parents=True, exist_ok=True)
    (SEEDS / "reference").mkdir(parents=True, exist_ok=True)
    ids = Ids()

    products, offers = load_catalogue()
    new_product_key = pick_new_product(products)
    print("new product (issue 2):", new_product_key)
    merchant = offers.dropna(subset=["store_merchant_id"]).groupby("brand_code")["store_merchant_id"].first().to_dict()

    mapping = build_mapping_seeds(products, offers, new_product_key)
    rules = build_campaign_rules(products)
    accounts = build_accounts()
    campaigns, issues = build_campaigns(accounts, products, new_product_key)

    # Fix rows added after the alerts (fixed_in_version = 1)
    sugar_rule = rules[(rules.brand_code == "PHR") & rules.match_token.str.contains("bloodsugar")]
    if not sugar_rule.empty:
        rules.loc[len(rules)] = {"brand_code": "PHR", "match_token": "bloodsugr", "campaign_id": None,
                                 "product_key": sugar_rule.iloc[0].product_key, "fixed_in_version": 1,
                                 "note": "alias for a misspelled live campaign; naming fixed in Ads Manager"}
    wrong_brand = campaigns[campaigns.campaign_name.str.startswith("PHR_") & (campaigns.brand_code == "PUR")]
    for _, c in wrong_brand.iterrows():
        rules.loc[len(rules)] = {"brand_code": "PUR", "match_token": None, "campaign_id": c.campaign_id,
                                 "product_key": c.product_key, "fixed_in_version": 1,
                                 "note": "campaign-level override: wrong brand prefix in name, renamed at source"}
    new_campaign = campaigns[campaigns.product_key == new_product_key]
    new_token = products.set_index("product_key").loc[new_product_key, "token"]
    rules.loc[rules.product_key == new_product_key, "fixed_in_version"] = 1
    rules.loc[rules.product_key == new_product_key, "note"] = "new product: rule added after the unmapped alert"

    ad_accounts_seed = accounts[["platform", "account_id", "account_name", "brand_code", "account_timezone",
                                 "currency"]].copy()
    ad_accounts_seed["fixed_in_version"] = np.where(ad_accounts_seed.account_id == "act_1011223399777", 1, 0)

    ads = simulate_ads(accounts, campaigns)
    camp = campaigns.set_index("campaign_id")
    acc = accounts.set_index("account_id")
    prod = products.set_index("product_key")
    offers_by_product = {k: g for k, g in offers.groupby("product_key")}

    # customers ---------------------------------------------------------
    customers = []          # dicts
    customers_by_brand = {b: [] for b in BRAND_WEIGHT}

    def new_customer(brand, day):
        ids.customer += 1
        country, currency, _ = COUNTRIES[rng.choice(len(COUNTRIES), p=[c[2] for c in COUNTRIES])]
        if brand == "PHR" and day >= pd.Timestamp("2025-03-01") and rng.random() < 0.5 and country == "US":
            pass
        c = {"customer_id": f"C{ids.customer:07d}", "email_sha256": sha256(f"customer{ids.customer}@example.com"),
             "country": country, "currency": currency, "first_brand": brand, "first_day": day}
        customers.append(c)
        customers_by_brand[brand].append(len(customers) - 1)
        return c

    def existing_customer(brand):
        pool = customers_by_brand[brand]
        if not pool or rng.random() < 0.12:   # 12% of repeat buyers come from another brand of the group
            all_idx = len(customers)
            return customers[int(rng.integers(0, all_idx))] if all_idx else None
        return customers[pool[int(rng.integers(0, len(pool)))]]

    orders, lines, payments, subs, sub_events, shipments = [], [], [], [], [], []
    wh_sku = mapping[mapping.source_system == "warehouse"].set_index("product_key")["source_sku"].to_dict()

    def launch_ok(key, day):
        return key != new_product_key or day >= NEW_PRODUCT_LAUNCH

    offer_sampler = {}
    for (key, ptype), group in offers.groupby(["product_key", "purchase_type"]):
        weights = np.array([{1: 0.45, 2: 0.3, 3: 0.35, 6: 0.2}.get(int(s), 0.1) for s in group.bundle_size])
        offer_sampler[(key, ptype)] = (list(group.itertuples(index=False)), weights / weights.sum())

    def choose_offer(product_key, purchase_type):
        records, weights = offer_sampler.get((product_key, purchase_type)) or offer_sampler[(product_key, "one_time")]
        return records[int(rng.choice(len(records), p=weights))]

    product_sampler = {}
    for brand in BRAND_WEIGHT:
        group = products[products.brand_code == brand]
        product_sampler[brand] = (group.product_key.tolist(), (group.popularity / group.popularity.sum()).values)

    def sample_product(brand, exclude=None, day=None):
        keys, weights = product_sampler[brand]
        for _ in range(20):
            key = keys[int(rng.choice(len(keys), p=weights))]
            if key != exclude and (day is None or launch_ok(key, day)):
                return key
        return keys[int(np.argmax(weights))]

    def add_payment(order, amount_local, currency, ts_utc, kind="charge", related=None, batch="api"):
        ids.payment += 1
        processor = "paypal" if rng.random() < 0.18 else "stripe"
        cents = int(round(amount_local * 100))
        fee = int(round(cents * 0.029 + 30)) if kind == "charge" else (1500 if kind == "chargeback" else 0)
        payout = ts_utc + timedelta(days=2 if ts_utc.weekday() < 3 else 4)
        payments.append({"payment_id": f"pay_{ids.payment:08d}", "order_id": order, "type": kind,
                         "processor": processor, "amount": cents if kind == "charge" else -cents,
                         "currency": currency.lower(), "fee": fee,
                         "created": int(pd.Timestamp(ts_utc).timestamp()), "status": "succeeded",
                         "payout_id": f"po_{pd.Timestamp(payout).strftime('%Y%m%d')}_{processor[:2]}",
                         "related_payment_id": related, "import_batch": batch})
        return f"pay_{ids.payment:08d}"

    def create_order(day, brand, customer, items, source, utm_source=None, campaign_id=None, subscription_id=None,
                     local_time=None):
        """items: list of (offer_row, quantity_of_items). Returns order id."""
        ids.order += 1
        order_id = f"{merchant.get(brand, brand)}-{ids.order}"
        if local_time is None:
            hour = int(rng.choice(24, p=HOUR_WEIGHTS))
            local_time = day + pd.Timedelta(hours=hour, minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))
        currency = customer["currency"]
        rate = fx_rate(currency, day)
        subtotal = 0.0
        for n, (offer, qty) in enumerate(items, start=1):
            unit_usd = float(offer.unit_price)
            if int(offer.store_qty) == 1 and int(offer.bundle_size) > 1:
                item_price_usd = unit_usd * int(offer.bundle_size)       # one SKU = the whole bundle
            else:
                item_price_usd = unit_usd                               # one SKU = one bottle
            item_price = round(item_price_usd / rate, 2) if currency != "USD" else round(item_price_usd, 2)
            lines.append({"order_id": order_id, "line_number": n, "sku": offer.store_sku, "quantity": int(qty),
                          "unit_price": item_price, "line_discount": 0.0})
            subtotal += item_price * qty
        discount = round(subtotal * 0.10, 2) if (source == "web" and rng.random() < 0.12) else 0.0
        units = sum(qty * (int(o.bundle_size) if int(o.store_qty) == 1 and int(o.bundle_size) > 1 else 1)
                    for o, qty in items)
        shipping = 0.0 if units >= 3 or source == "subscription_renewal" else round(9.95 / rate, 2)
        total = round(subtotal - discount + shipping, 2)
        created_utc = local_to_utc(local_time)
        orders.append({"order_id": order_id, "store": merchant.get(brand, brand), "brand_code_hint": None,
                       "created_at": fmt(local_time), "store_timezone": STORE_TZ,
                       "customer_id": customer["customer_id"], "customer_email_sha256": customer["email_sha256"],
                       "ship_country": customer["country"], "currency": currency,
                       "subtotal": round(subtotal, 2), "discount_total": discount, "shipping_total": shipping,
                       "order_total": total, "order_source": source, "utm_source": utm_source,
                       "utm_campaign_id": campaign_id, "subscription_id": subscription_id,
                       "webhook_event_id": f"evt_{sha256(order_id)[:16]}",
                       "_received_at": fmt(created_utc + timedelta(seconds=int(rng.integers(2, 90))))})
        # payment captured a few seconds after checkout
        add_payment(order_id, total, currency, created_utc + timedelta(seconds=int(rng.integers(1, 20))))
        # shipment from the 3PL 1-3 days later
        ids.shipment += 1
        ship_utc = created_utc + timedelta(days=int(rng.integers(1, 4)), hours=int(rng.integers(0, 8)))
        for offer, qty in items:
            bottles = qty * (int(offer.bundle_size) if int(offer.store_qty) == 1 and int(offer.bundle_size) > 1 else 1)
            shipments.append({"shipment_id": f"SH{ids.shipment:08d}", "order_ref": order_id.split("-")[-1],
                              "warehouse_sku": wh_sku[offer.product_key], "quantity": int(bottles),
                              "shipped_at_utc": fmt(ship_utc), "status": "shipped", "returned_at_utc": None})
        return order_id, created_utc, total, currency

    # Subscription lifecycle --------------------------------------------
    def run_subscription(sub_id, brand, customer, offer, start_utc, start_local):
        interval = 30 * int(offer.bundle_size)
        state_t = start_local
        events = [("created", start_utc)]
        status, cancelled_at, reason = "ACTIVE", None, None
        cycle = 1
        next_charge = start_local + pd.Timedelta(days=interval)
        while state_t <= END:
            # voluntary cancellation before the next charge
            p_cancel = max(0.08, 0.24 - 0.04 * (cycle - 1))
            if rng.random() < p_cancel:
                t = state_t + pd.Timedelta(days=int(rng.integers(5, max(6, interval - 2))), hours=int(rng.integers(8, 22)))
                if t > END:
                    break
                events.append(("cancelled", local_to_utc(t)))
                status, cancelled_at, reason = "CANCELLED", local_to_utc(t), str(rng.choice(
                    ["too_expensive", "have_enough", "not_seeing_results", "other"], p=[0.35, 0.3, 0.2, 0.15]))
                # small share comes back
                if rng.random() < 0.05:
                    back = t + pd.Timedelta(days=int(rng.integers(20, 90)))
                    if back <= END:
                        events.append(("reactivated", local_to_utc(back)))
                        status, cancelled_at, reason = "ACTIVE", None, None
                        state_t, next_charge = back, back
                        cycle += 1
                        continue
                break
            # pause
            if rng.random() < 0.06:
                t = state_t + pd.Timedelta(days=int(rng.integers(3, max(4, interval - 3))), hours=10)
                resume = t + pd.Timedelta(days=int(rng.integers(30, 75)))
                if t > END:
                    break
                events.append(("paused", local_to_utc(t)))
                if resume > END:
                    break
                events.append(("resumed", local_to_utc(resume)))
                next_charge = resume
            # charge attempt with retries (dunning)
            charged = False
            attempt_t = next_charge
            for attempt, p_ok in enumerate([0.91, 0.5, 0.4]):
                if attempt_t > END + pd.Timedelta(hours=23):
                    break
                if rng.random() < p_ok:
                    charged = True
                    break
                events.append(("charge_failed", local_to_utc(attempt_t)))
                attempt_t = attempt_t + pd.Timedelta(days=[3, 4, 0][attempt])
            if attempt_t > END + pd.Timedelta(hours=23):
                break
            if charged:
                day = attempt_t.normalize()
                oid, ts, _, _ = create_order(day, brand, customer, [(offer, 1)], "subscription_renewal",
                                             subscription_id=sub_id, local_time=attempt_t)
                events.append(("charge_succeeded", ts))
                state_t = attempt_t
                next_charge = attempt_t + pd.Timedelta(days=interval)
                cycle += 1
            else:
                t = attempt_t + pd.Timedelta(days=1)
                if t > END:
                    break
                events.append(("cancelled", local_to_utc(t)))
                status, cancelled_at, reason = "CANCELLED", local_to_utc(t), "payment_failed"
                break
        for event_type, ts in events:
            ids.event += 1
            sub_events.append({"event_id": f"se_{ids.event:08d}", "subscription_id": sub_id,
                               "event_type": event_type, "occurred_at": fmt(ts)})
        failures = sum(1 for e, _ in events if e == "charge_failed")
        last_event = max(ts for _, ts in events)
        subs.append({"subscription_id": sub_id, "customer_id": customer["customer_id"],
                     "store": merchant.get(brand, brand), "sku": offer.store_sku, "quantity": 1,
                     "price": float(offer.unit_price) * (int(offer.bundle_size) if int(offer.store_qty) == 1 else 1),
                     "order_interval_frequency": interval, "order_interval_unit": "day",
                     "status": status, "created_at": fmt(start_utc), "updated_at": fmt(last_event),
                     "cancelled_at": fmt(cancelled_at), "cancellation_reason": reason,
                     "failed_charge_count": failures})

    def new_purchase(day, brand, product_key, source, utm_source=None, campaign_id=None, customer=None):
        customer = customer or new_customer(brand, day)
        has_sub = (product_key, "subscribe_save") in offer_sampler
        purchase_type = "subscribe_save" if has_sub and rng.random() < 0.33 else "one_time"
        offer = choose_offer(product_key, purchase_type)
        items = [(offer, 1 if int(offer.store_qty) == 1 and int(offer.bundle_size) > 1 or purchase_type == "subscribe_save"
                  else int(offer.bundle_size))]
        # cross-sell a second product of the same brand
        if rng.random() < 0.15:
            other_key = sample_product(brand, exclude=product_key, day=day)
            if other_key != product_key:
                extra = choose_offer(other_key, "one_time")
                items.append((extra, 1 if int(extra.store_qty) == 1 and int(extra.bundle_size) > 1 else int(extra.bundle_size)))
        oid, ts, total, currency = create_order(day, brand, customer, items, "web", utm_source, campaign_id)
        if purchase_type == "subscribe_save":
            ids.subscription += 1
            sub_id = f"sub_{ids.subscription}"
            orders[-1]["subscription_id"] = sub_id
            local_time = pd.Timestamp(orders[-1]["created_at"])
            run_subscription(sub_id, brand, customer, offer, ts, local_time)
        return oid

    # paid orders, driven by the ad delivery --------------------------------
    print("simulating orders ...")
    for row in ads.itertuples():
        if row.true_orders == 0:
            continue
        c = camp.loc[row.campaign_id]
        for _ in range(row.true_orders):
            key = c.product_key if rng.random() < 0.8 else sample_product(c.brand_code, day=row.date)
            if not launch_ok(key, row.date):
                key = c.product_key
            returning = existing_customer(c.brand_code) if rng.random() < 0.08 else None
            new_purchase(row.date, c.brand_code, key, "web", c.platform if c.platform != "meta" else "facebook",
                         row.campaign_id, returning)

    # organic, e-mail and direct orders ----------------------------------------
    for day in DAYS:
        for brand, weight in BRAND_WEIGHT.items():
            n = rng.poisson(13 * weight * seasonality(day))
            for _ in range(n):
                key = sample_product(brand, day=day)
                channel = rng.choice(["email", "organic", "direct"], p=[0.45, 0.30, 0.25])
                returning = existing_customer(brand) if (channel == "email" or rng.random() < 0.3) else None
                new_purchase(day, brand, key, "web", str(channel), None, returning)

    orders_df = pd.DataFrame(orders)
    lines_df = pd.DataFrame(lines)
    payments_df = pd.DataFrame(payments)
    subs_df = pd.DataFrame(subs)
    events_df = pd.DataFrame(sub_events)
    ship_df = pd.DataFrame(shipments)
    print(f"{len(orders_df):,} orders, {len(subs_df):,} subscriptions, {len(payments_df):,} payments")

    # refunds and chargebacks (365-day guarantee: long tail) ------------------
    charges = payments_df[payments_df.type == "charge"].merge(
        orders_df[["order_id", "order_total"]], on="order_id")
    refund_rows = []
    for ch in charges.itertuples():
        r = rng.random()
        created = pd.Timestamp(ch.created, unit="s")
        if r < 0.055:
            delay = int(min(rng.exponential(35) + 3, 360))
            kind, amount = "refund", ch.order_total if rng.random() < 0.8 else round(ch.order_total * 0.5, 2)
        elif r < 0.059:
            delay = int(rng.integers(25, 95))
            kind, amount = "chargeback", ch.order_total
        else:
            continue
        ts = created + timedelta(days=delay, hours=int(rng.integers(0, 12)))
        if ts > pd.Timestamp(END) + timedelta(days=40):     # data extracted on 2026-11-09
            continue
        refund_rows.append((ch.order_id, amount, ch.currency.upper(), ts, kind, ch.payment_id))
    # Issue 6: dispute wave - extra chargebacks on February/March orders, filed in May
    wave = charges[charges.created.between(pd.Timestamp("2026-02-15").timestamp(), pd.Timestamp("2026-03-31").timestamp())]
    wave = wave.sample(min(140, len(wave)), random_state=SEED)
    for ch in wave.itertuples():
        refund_rows.append((ch.order_id, ch.order_total, ch.currency.upper(),
                            pd.Timestamp("2026-05-05") + timedelta(days=int(rng.integers(0, 20))), "chargeback",
                            ch.payment_id))
    issues.append({"issue_type": 6, "description": "Dispute wave: 140 late chargebacks on Feb-Mar 2026 orders, "
                   "filed in May after the books were closed", "detect_key": CHARGEBACK_WAVE_MONTH})
    for order_id, amount, currency, ts, kind, related in refund_rows:
        add_payment(order_id, amount, currency, ts.to_pydatetime(), kind, related)
        if kind == "refund" and rng.random() < 0.5:
            ref = order_id.split("-")[-1]
            ship_df.loc[ship_df.order_ref == ref, ["status", "returned_at_utc"]] = ["returned", fmt(ts - timedelta(days=2))]
    payments_df = pd.DataFrame(payments)

    # Issue 8: a manual PayPal import stored amounts in units instead of cents
    candidates = payments_df[(payments_df.type == "charge") & (payments_df.processor == "paypal") &
                             (payments_df.created.between(pd.Timestamp("2026-04-01").timestamp(),
                                                          pd.Timestamp("2026-04-30").timestamp()))]
    bug = candidates.sample(min(25, len(candidates)), random_state=SEED).index
    payments_df["amount"] = payments_df["amount"].astype("float64")
    payments_df.loc[bug, "amount"] = (payments_df.loc[bug, "amount"] / 100).round(2)
    payments_df.loc[bug, "import_batch"] = CENTS_BUG_BATCH
    for order_id in payments_df.loc[bug, "order_id"].head(3):
        pass
    issues.append({"issue_type": 8, "description": "25 PayPal charges imported manually with amounts in units "
                   "instead of cents", "detect_key": payments_df.loc[bug[0], "order_id"]})
    issues.append({"issue_type": 8, "description": "Orders in EUR and GBP next to USD; payment amounts in cents vs "
                   "shop amounts in units (structural, handled in staging)", "detect_key": None})

    # Issue 5a: webhook replays create duplicate order rows
    dupes = orders_df.sample(frac=0.004, random_state=SEED).copy()
    dupes["_received_at"] = (pd.to_datetime(dupes["_received_at"]) + pd.Timedelta(minutes=17)).dt.strftime("%Y-%m-%d %H:%M:%S")
    orders_df = pd.concat([orders_df, dupes], ignore_index=True)
    issues.append({"issue_type": 5, "description": f"{len(dupes)} orders delivered twice by the shop webhook (replay)",
                   "detect_key": dupes.iloc[0].order_id})

    # Issue 9: tool status says ACTIVE while the subscription is paused or failing
    paused_now = events_df.sort_values("occurred_at").groupby("subscription_id").tail(1)
    paused_ids = paused_now[paused_now.event_type.isin(["paused", "charge_failed"])].subscription_id
    if len(paused_ids):
        issues.append({"issue_type": 9, "description": f"{len(paused_ids)} subscriptions paused or in payment failure "
                       "still carry status ACTIVE in the subscription tool", "detect_key": paused_ids.iloc[0]})

    # ad platform raw tables -------------------------------------------------
    print("writing ad connectors ...")
    ads = ads.merge(campaigns[["campaign_id", "campaign_name", "platform", "brand_code", "product_key"]],
                    on="campaign_id")
    attributed = orders_df.drop_duplicates("order_id").dropna(subset=["utm_campaign_id"])
    attributed = attributed.assign(day=pd.to_datetime(attributed.created_at).dt.normalize())
    value = attributed.groupby(["utm_campaign_id", "day"]).agg(fp_orders=("order_id", "count"),
                                                               fp_value=("order_total", "sum")).reset_index()
    ads = ads.merge(value, left_on=["campaign_id", "date"], right_on=["utm_campaign_id", "day"], how="left")
    ads[["fp_orders", "fp_value"]] = ads[["fp_orders", "fp_value"]].fillna(0)
    # Issue 7: platforms count view-through and 7-day click conversions -> more than real orders
    inflation = np.where(ads.platform == "meta", rng.uniform(1.25, 1.65, len(ads)), rng.uniform(1.05, 1.3, len(ads)))
    ads["platform_conversions"] = np.round(ads.fp_orders * inflation + rng.poisson(0.3, len(ads)), 0)
    ads["platform_value_usd"] = np.round(ads.fp_value * inflation, 2)
    issues.append({"issue_type": 7, "description": "Platform-reported conversions exceed real orders "
                   "(view-through and 7-day click windows)", "detect_key": None})
    issues.append({"issue_type": 4, "description": "Store reports in New York time, Google Ads accounts in Los Angeles "
                   "time, the EU Meta account in Vilnius time, payments in UTC", "detect_key": None})

    meta_rows, google_rows = [], []
    for r in ads.itertuples():
        account = acc.loc[r.account_id]
        rate = fx_rate(account.currency, r.date)
        spend = r.spend_usd / rate
        value_acc = r.platform_value_usd / rate
        clicks = int(max(1, rng.poisson(spend / rng.uniform(1.1, 2.4))))
        impressions = int(clicks * rng.uniform(55, 120))
        if r.platform == "meta":
            loaded = r.date + pd.Timedelta(days=1, hours=6)
            batch = "daily"
            if r.account_id == "act_1011223399777" and r.date < CONNECTOR_PICKUP:
                loaded, batch = pd.Timestamp("2026-05-21 06:00"), "backfill"
            for adset, share in (("prospecting", 0.7), ("retargeting", 0.3)):
                meta_rows.append({"date_start": r.date.strftime("%Y-%m-%d"), "account_id": r.account_id,
                                  "account_name": account.account_name, "account_currency": account.currency,
                                  "account_timezone": account.account_timezone, "campaign_id": r.campaign_id,
                                  "campaign_name": r.campaign_name, "adset_id": f"{r.campaign_id}{1 if adset == 'prospecting' else 2}",
                                  "adset_name": f"{adset} | broad | 25-65+", "spend": f"{spend * share:.2f}",
                                  "impressions": int(impressions * share), "clicks": int(clicks * share),
                                  "actions_purchase": float(round(r.platform_conversions * share, 0)),
                                  "action_values_purchase": round(value_acc * share, 2),
                                  "_loaded_at": fmt(loaded), "_load_batch": batch})
        else:
            google_rows.append({"segments_date": r.date.strftime("%Y-%m-%d"), "customer_id": r.account_id,
                                "customer_descriptive_name": account.account_name,
                                "customer_currency_code": account.currency, "customer_time_zone": account.account_timezone,
                                "campaign_id": int(r.campaign_id), "campaign_name": r.campaign_name,
                                "metrics_cost_micros": int(round(spend * 1_000_000)),
                                "metrics_impressions": impressions, "metrics_clicks": clicks,
                                "metrics_conversions": float(r.platform_conversions),
                                "metrics_conversions_value": round(value_acc, 2),
                                "_loaded_at": fmt(r.date + pd.Timedelta(days=1, hours=5))})
    meta = pd.DataFrame(meta_rows)
    # Issue 5b: the Meta connector loads one day twice
    dup_day = meta[meta.date_start == DUPLICATE_LOAD_DAY.strftime("%Y-%m-%d")].copy()
    dup_day["_loaded_at"] = fmt(DUPLICATE_LOAD_DAY + pd.Timedelta(days=2, hours=6))
    dup_day["_load_batch"] = "resync"
    meta = pd.concat([meta, dup_day], ignore_index=True)
    issues.append({"issue_type": 5, "description": "Meta connector re-synced 2026-05-14: every row loaded twice",
                   "detect_key": DUPLICATE_LOAD_DAY.strftime("%Y-%m-%d")})
    issues.append({"issue_type": 1, "description": "New VitalPeak Meta account (act_1011223399777) missing from the "
                   "connector for its first 5 days and absent from the account mapping",
                   "detect_key": "act_1011223399777"})
    issues.append({"issue_type": 2, "description": f"New product {new_product_key} launched {NEW_PRODUCT_LAUNCH.date()} "
                   "with no row in the product mapping", "detect_key": offers[offers.product_key == new_product_key].store_sku.iloc[0]})
    google = pd.DataFrame(google_rows)

    # Monthly invoices from the platforms (true spend, account currency)
    billing = ads.assign(month=ads.date.dt.to_period("M").astype(str)).merge(
        accounts[["account_id", "currency"]], on="account_id")
    billing["spend_acc"] = billing.apply(lambda r: r.spend_usd / fx_rate(r.currency, r.date), axis=1)
    billing = billing.groupby(["platform", "account_id", "month", "currency"], as_index=False)["spend_acc"].sum()
    billing["invoice_id"] = "INV-" + billing.platform.str[:2].str.upper() + "-" + billing.month.str.replace("-", "") + \
        "-" + billing.account_id.str[-4:]
    billing = billing.rename(columns={"spend_acc": "invoiced_amount"}).round({"invoiced_amount": 2})

    # CRM contacts (hashed e-mails only; some leads never bought)
    cust_df = pd.DataFrame(customers)
    crm = cust_df[["email_sha256", "first_brand", "first_day", "country"]].copy()
    crm["crm_contact_id"] = [f"crm_{i:07d}" for i in range(1, len(crm) + 1)]
    crm["signup_at"] = (crm.first_day - pd.to_timedelta(rng.integers(0, 3, len(crm)), unit="D")).dt.strftime("%Y-%m-%d")
    crm["marketing_opt_in"] = rng.random(len(crm)) < 0.72
    leads = pd.DataFrame({"email_sha256": [sha256(f"lead{i}@example.com") for i in range(int(len(crm) * 0.35))]})
    leads["first_brand"] = rng.choice(list(BRAND_WEIGHT), len(leads), p=list(BRAND_WEIGHT.values()))
    leads["signup_at"] = pd.to_datetime(rng.choice(DAYS, len(leads))).strftime("%Y-%m-%d")
    leads["country"] = "US"
    leads["crm_contact_id"] = [f"crm_{i:07d}" for i in range(len(crm) + 1, len(crm) + len(leads) + 1)]
    leads["marketing_opt_in"] = True
    crm = pd.concat([crm.drop(columns="first_day"), leads], ignore_index=True)
    crm = crm.rename(columns={"first_brand": "signup_brand"})

    # Finance month close: net revenue (USD) as known 5 days after each month end
    pay = payments_df.copy()
    pay["ts"] = pd.to_datetime(pay.created, unit="s")
    order_month = orders_df.drop_duplicates("order_id").assign(
        month=pd.to_datetime(orders_df.drop_duplicates("order_id").created_at).dt.to_period("M"))[["order_id", "month"]]
    pay = pay.merge(order_month, on="order_id")
    pay["usd"] = pay.apply(lambda r: r.amount / 100 * fx_rate(r.currency.upper(), r.ts), axis=1)
    pay.loc[pay.import_batch == CENTS_BUG_BATCH, "usd"] *= 100        # Finance booked the corrected amount
    close_rows = []
    for month in pd.period_range(START, END, freq="M"):
        cutoff = (month.end_time + pd.Timedelta(days=5)).tz_localize(STORE_TZ).tz_convert("UTC").tz_localize(None)
        known = pay[(pay.month == month) & (pay.ts <= cutoff)]
        close_rows.append({"month": str(month), "closed_on": (month.end_time + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                           "booked_gross_revenue_usd": round(known[known.type == "charge"].usd.sum(), 2),
                           "booked_refunds_usd": round(-known[known.type != "charge"].usd.sum(), 2),
                           "booked_net_revenue_usd": round(known.usd.sum(), 2)})
    close = pd.DataFrame(close_rows)

    # ------------------------------------------------------------------ write
    raw = {
        "raw_shop_orders": orders_df.drop(columns=["brand_code_hint"]),
        "raw_shop_order_lines": lines_df,
        "raw_subscriptions": subs_df,
        "raw_subscription_events": events_df,
        "raw_payments": payments_df,
        "raw_fulfillment": ship_df,
        "raw_meta_ads": meta,
        "raw_google_ads": google,
        "raw_ad_billing": billing[["invoice_id", "platform", "account_id", "month", "currency", "invoiced_amount"]],
        "raw_crm_customers": crm[["crm_contact_id", "email_sha256", "signup_brand", "signup_at", "country",
                                  "marketing_opt_in"]],
        "raw_finance_month_close": close,
    }
    for name, frame in raw.items():
        frame.to_parquet(OUT / f"{name}.parquet", index=False)
        print(f"  {name}: {len(frame):,} rows")

    issues_df = pd.DataFrame(issues)
    issues_df.insert(0, "issue_id", range(1, len(issues_df) + 1))
    issues_df.to_csv(OUT / "seed_injected_issues.csv", index=False)

    mapping.to_csv(SEEDS / "mapping" / "product_mapping.csv", index=False)
    rules.to_csv(SEEDS / "mapping" / "campaign_product_rules.csv", index=False)
    ad_accounts_seed.to_csv(SEEDS / "mapping" / "ad_accounts.csv", index=False)
    pd.DataFrame([{"brand_code": b, "brand_token": t} for b, ts in BRAND_TOKENS.items() for t in ts]).to_csv(
        SEEDS / "mapping" / "brand_name_tokens.csv", index=False)
    store_map = pd.DataFrame([{"store": merchant.get(b, b), "brand_code": b} for b in BRAND_WEIGHT])
    store_map.to_csv(SEEDS / "mapping" / "store_brand.csv", index=False)
    fx_rows = [{"month": str(m), "currency": c, "usd_per_unit": FX[c][i]} for i, m in enumerate(FX_MONTHS) for c in FX]
    fx_rows += [{"month": str(m), "currency": "USD", "usd_per_unit": 1.0} for m in FX_MONTHS]
    pd.DataFrame(fx_rows).to_csv(SEEDS / "reference" / "fx_rates_monthly.csv", index=False)
    print(f"issues injected: {len(issues_df)} rows, mapping rows: {len(mapping)}, campaign rules: {len(rules)}")


HOUR_WEIGHTS = np.array([2, 1.5, 1, 0.8, 0.8, 1, 2, 3, 4, 5, 5.5, 6, 6, 5.5, 5.5, 5.5, 6, 6.5, 7, 7.5, 7.5, 7, 5, 3.5])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

if __name__ == "__main__":
    main()
