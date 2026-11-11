"""Build the PDF report: HTML pages with matplotlib charts (inline SVG), printed to PDF by
Microsoft Edge (or Chrome) in headless mode. Landscape 16:9, one conclusion per page.

Usage (from the repository root, after `dbt build` and the before-fix replay):
  python src/build_report.py
Outputs: docs/report.html, docs/ImpactBrands_DataCaseStudy.pdf, docs/img/page_XX.png
"""
import base64
import io
import os
import shutil
import subprocess
from html import escape
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.dates
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DBT = ROOT / "dbt"
DOCS = ROOT / "docs"
PUBLIC = ROOT / "data" / "public"

BLUE, DARK, LIGHT, PALE = "#2A78D6", "#1C5CAB", "#86B6EF", "#CDE2FB"
GREY, LIGHTGREY, RED, TEXT, SUB = "#898781", "#C9C7C0", "#D03B3B", "#0B0B0B", "#52514E"
BRAND_ORDER = ["PHR", "NHMD", "PUR", "NBL", "TRU", "PET", "VPK"]
BRAND_NAME = {"PHR": "PureHealth Research", "NHMD": "Nation Health MD", "PUR": "Pureance", "TRU": "Trumeta",
              "PET": "PetMade", "NBL": "Nature's Blast", "VPK": "VitalPeak"}
SNAPSHOT = "2026-11-11"
FOOTER_NOTE = "Independent case study based on public data · not affiliated with or endorsed by Impact Brands"
AI_NOTE = ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined the "
           "questions, chose and validated the data sources, made the modelling decisions and checked every result.")

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "svg.fonttype": "none",
    "axes.edgecolor": LIGHTGREY, "axes.labelcolor": SUB, "xtick.color": GREY, "ytick.color": GREY,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#E1E0D9",
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False, "legend.fontsize": 9,
    "figure.facecolor": "none", "axes.facecolor": "none",
})


# ------------------------------------------------------------------ helpers
def svg(fig):
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    text = buffer.getvalue()
    return text[text.find("<svg"):]


def money(x, decimals=0):
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.{max(decimals, 2)}f}M"
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.{decimals}f}K"
    return f"${x:,.{decimals}f}"


def pct(x, decimals=0):
    return f"{x * 100:.{decimals}f}%"


def table(frame, align=None, highlight_col=None, small=False):
    align = align or {}
    head = "".join(f"<th style='text-align:{align.get(c, 'left')}'>{escape(str(c))}</th>" for c in frame.columns)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for c in frame.columns:
            value = row[c]
            style = f"text-align:{align.get(c, 'left')}"
            if highlight_col and c == highlight_col[0] and highlight_col[1](value):
                style += f";color:{RED};font-weight:600"
            cells.append(f"<td style='{style}'>{value}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table class='{'small' if small else ''}'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def card(title, body, cls="", style=""):
    title_html = f"<div class='card-title'>{title}</div>" if title else ""
    return f"<div class='card {cls}' style='{style}'>{title_html}<div class='card-body'>{body}</div></div>"


def kpi(label, value, note, tag=""):
    tag_html = f"<div class='kpi-tag'>{tag}</div>" if tag else ""
    return (f"<div class='card kpi'>{tag_html}<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div><div class='kpi-note'>{note}</div></div>")


def page(number, tag, title, subtitle, body, footer_sources):
    tag_html = f"<div class='tag'>{tag}</div>" if tag else ""
    return f"""
<section class="page">
  <header><div><h1>{title}</h1><p class="subtitle">{subtitle}</p></div>{tag_html}</header>
  <main>{body}</main>
  <footer><span>{footer_sources}</span><span>{FOOTER_NOTE}</span><span class="num">{number}</span></footer>
</section>"""


def img_base64(path, style=""):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f"<img src='data:image/png;base64,{data}' style='{style}'/>"


# ------------------------------------------------------------------ data
class Data:
    def __init__(self):
        os.chdir(DBT)  # staging views read ../data/simulated/*.parquet relative to dbt/
        self.db = duckdb.connect("impact_brands.duckdb", read_only=True)
        self.db0 = duckdb.connect("impact_brands_before_fix.duckdb", read_only=True)
        self.products = pd.read_csv(PUBLIC / "catalog_products.csv")
        self.products = self.products[~self.products.is_gift_card]
        self.offers = pd.read_csv(PUBLIC / "catalog_offers.csv")
        self.first_seen = pd.read_csv(PUBLIC / "product_first_seen.csv", parse_dates=["first_seen"])
        self.history = pd.read_csv(PUBLIC / "price_history.csv", parse_dates=["capture_date"])
        self.trends = pd.read_csv(PUBLIC / "trends_monthly.csv", parse_dates=["month"])
        self.detection = pd.read_csv(ROOT / "data" / "simulated" / "detection_results.csv")

    def q(self, sql, before_fix=False):
        return (self.db0 if before_fix else self.db).sql(sql).df()


# ------------------------------------------------------------------ pages
def page_portfolio(d):
    p = d.products
    stats = p.groupby("brand_code").agg(
        products=("product_slug", "count"), price=("one_time_price_1", "median"),
        sub_share=("has_subscribe_save", lambda s: s.dropna().astype(bool).mean() if s.notna().any() else np.nan),
        reviews=("site_rating_count", "sum"), rating=("site_rating_value", "median")).reindex(BRAND_ORDER)
    total, reviews = int(stats.products.sum()), stats.reviews.sum()
    top2 = stats.loc[["PHR", "NHMD"]]
    share_products, share_reviews = top2.products.sum() / total, top2.reviews.sum() / reviews

    fig, ax = plt.subplots(figsize=(5.6, 2.9))
    cats = p.groupby(["brand_code", "category"]).size().unstack(fill_value=0).reindex(BRAND_ORDER)
    top_cats = p.category.value_counts().index[:6]
    cats["Other"] = cats.drop(columns=top_cats).sum(axis=1)
    cats = cats[list(top_cats) + ["Other"]]
    colors = [DARK, BLUE, LIGHT, PALE, "#5E8FC9", "#A9C8EE", LIGHTGREY]
    left = np.zeros(len(cats))
    for color, column in zip(colors, cats.columns):
        ax.barh([BRAND_NAME[b] for b in cats.index], cats[column], left=left, color=color, label=column, height=0.65)
        left += cats[column].values
    for i, v in enumerate(left):
        ax.text(v + 1, i, str(int(v)), va="center", fontsize=9, color=SUB)
    ax.invert_yaxis(); ax.grid(axis="y", visible=False); ax.set_xlabel("products in the online catalogue")
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.45, -0.52), fontsize=8)
    chart_products = svg(fig)

    fig, ax = plt.subplots(figsize=(4.3, 2.7))
    r = stats.reviews.fillna(0)
    ax.bar([b for b in r.index], r.values, color=[BLUE if b in ("PHR", "NHMD") else LIGHTGREY for b in r.index])
    for i, v in enumerate(r.values):
        ax.text(i, v + 150, f"{int(v):,}", ha="center", fontsize=8, color=SUB)
    ax.set_ylabel("on-site reviews (sum)"); ax.grid(axis="x", visible=False)
    chart_reviews = svg(fig)

    tbl = pd.DataFrame({
        "Brand": [BRAND_NAME[b] for b in stats.index],
        "Focus": [d.q(f"select focus from marts.dim_brand where brand_code='{b}'").focus[0] for b in stats.index],
        "Products": stats.products.astype(int),
        "Median price, 1 unit": [f"${v:.2f}" if pd.notna(v) else "not shown" for v in stats.price],
        "Subscribe & save": [pct(v) if pd.notna(v) else "-" for v in stats.sub_share],
        "On-site rating": [f"{v:.1f}" if pd.notna(v) else "-" for v in stats.rating],
    })
    body = f"""
<div class="grid" style="grid-template-columns: 1.25fr 1fr; grid-template-rows: auto auto;">
  {card("Catalogue size and mix by brand (category labels from product names)", chart_products)}
  {card("Social proof is concentrated: on-site reviews by brand", chart_reviews)}
  {card("Brand scorecard (snapshot " + SNAPSHOT + ")", table(tbl, {"Products": "right", "Median price, 1 unit": "right", "Subscribe & save": "right", "On-site rating": "right"}, small=True))}
  {card("The company in public numbers", f'''
    <div class="facts">
      <div><b>402</b><span>team members (Aug 2025 press release)</span></div>
      <div><b>3.3M</b><span>people reached, per the company</span></div>
      <div><b>7</b><span>brands in the job post, 7 storefronts verified</span></div>
      <div><b>1</b><span>shared stack: same storefront and checkout platform on 6 stores</span></div>
    </div>
    <p class="note">Six stores show the same company address in their footer; VitalPeak is linked from the group site.
    Remote-first, data roles based in Lithuania. A "Tracking Systems &amp; Data" team sits under the CTO.</p>''')}
</div>"""
    title = (f"PureHealth Research and Nation Health MD carry {pct(share_products)} of the {total}-product catalogue "
             f"and {pct(share_reviews)} of on-site reviews")
    subtitle = ("Seven brands share one platform and one offer logic. One canonical product and brand model can serve "
                "all of them; the two largest brands set the volume the data model must handle.")
    return page(1, "PUBLIC DATA", title, subtitle, body,
                f"Sources: 7 brand storefronts (sitemaps + product pages), PR Newswire 29 Aug 2025, theimpactbrands.com · collected {SNAPSHOT}"), dict(total=total, share_products=share_products, share_reviews=share_reviews)


def page_pricing(d):
    o = d.offers.merge(d.products[["brand_code", "product_slug", "one_time_price_1"]], on=["brand_code", "product_slug"])
    o = o[o.bundle_size.isin([1, 3, 6])]
    o["relative"] = o.unit_price / o.one_time_price_1
    ladder = o.groupby(["purchase_type", "bundle_size"]).relative.median().unstack(0)

    fig, ax = plt.subplots(figsize=(4.3, 2.7))
    ax.plot(ladder.index, ladder["one_time"] * 100, marker="o", color=BLUE, lw=2.2, label="one-time purchase")
    ax.plot(ladder.index, ladder["subscribe_save"] * 100, marker="o", color=DARK, lw=2.2, ls="--", label="subscribe & save")
    for x in ladder.index:
        ax.annotate(f"{ladder.loc[x, 'one_time'] * 100:.0f}", (x, ladder.loc[x, "one_time"] * 100), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8, color=BLUE)
        ax.annotate(f"{ladder.loc[x, 'subscribe_save'] * 100:.0f}", (x, ladder.loc[x, "subscribe_save"] * 100), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color=DARK)
    ax.set_xticks([1, 3, 6]); ax.set_xticklabels(["1 unit", "3 units", "6 units"]); ax.set_ylim(35, 110)
    ax.set_ylabel("price per unit (1 unit one-time = 100)"); ax.legend(loc="lower left")
    chart_ladder = svg(fig)

    sub = d.products.dropna(subset=["subscribe_discount_pct"]).groupby("brand_code").subscribe_discount_pct.median().reindex(BRAND_ORDER).dropna()
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    ax.bar(sub.index, sub.values * 100, color=[BLUE if v > 0.15 else LIGHT for v in sub.values])
    for i, v in enumerate(sub.values):
        ax.text(i, v * 100 + 0.4, f"{v * 100:.1f}%", ha="center", fontsize=8, color=SUB)
    ax.set_ylabel("subscribe & save discount, 1 unit"); ax.grid(axis="x", visible=False); ax.set_ylim(0, 20)
    chart_sub = svg(fig)

    h = d.history[(d.history.purchase_type == "one_time") & (d.history.bundle_size == 1)]
    keep = {"liver-health-formula-supplement": "PHR Liver Health Formula", "lymph-system-support": "PHR Lymph System Support",
            "blood-sugar-formula-supplement": "PHR Blood Sugar Formula", "metabolic-reds": "TRU Metabolic Reds",
            "hip-and-joint-formula": "PET Hip & Joint Formula", "deepsea-collagen-marine-collagen-supplement": "PUR DeepSea Collagen"}
    fig, ax = plt.subplots(figsize=(4.6, 2.7))
    colors = [DARK, BLUE, LIGHT, GREY, "#5E8FC9", LIGHTGREY]
    for color, (slug, label) in zip(colors, keep.items()):
        s = h[h.product_slug == slug].groupby("capture_date").unit_price.min().sort_index()
        if len(s):
            ax.step(s.index, s.values, where="post", color=color, lw=1.8, label=label)
    ax.set_ylabel("1-unit one-time price, USD"); ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.tick_params(axis="x", labelsize=8)
    chart_history = svg(fig)

    fs = d.first_seen.copy()
    fs["year"] = fs.first_seen.dt.year
    launches = fs[fs.year >= 2022].groupby(["year", fs.brand_code.eq("PHR").map({True: "PureHealth Research", False: "other 6 brands"})]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    ax.bar(launches.index.astype(str), launches.get("PureHealth Research", 0), color=BLUE, label="PureHealth Research")
    ax.bar(launches.index.astype(str), launches.get("other 6 brands", 0), bottom=launches.get("PureHealth Research", 0), color=LIGHT, label="other 6 brands")
    ax.set_ylabel("product URLs first archived"); ax.legend(fontsize=8); ax.grid(axis="x", visible=False)
    chart_launch = svg(fig)

    six = 1 - ladder.loc[6, "one_time"]
    six_sub = 1 - ladder.loc[6, "subscribe_save"]
    list_gap = (1 - d.products.one_time_price_1 / d.products.list_unit_price).median()
    body = f"""
<div class="grid" style="grid-template-columns: 1fr 0.85fr 1.05fr; grid-template-rows: auto auto;">
  {card("The bundle ladder: price per unit by bundle size (median of all products)", chart_ladder)}
  {card("Two subscribe & save policies: 16.7% vs 10%", chart_sub)}
  {card("Archived 1-unit prices move in steps (Wayback Machine)", chart_history)}
  {card("Why this matters for the data model", f'''<ul class="bullets">
     <li>One product is sold as <b>6+ sellable offers</b> (1/3/6 units x one-time / subscription), each with its own store code. Revenue per product needs a mapping from every code to one product and a units-per-item factor.</li>
     <li>A crossed-out list price sits {pct(list_gap)} above the 1-unit price: "discount" must be defined once (vs list or vs 1-unit price).</li>
     <li>Subscriptions start at a discount and renew automatically: active subscriptions and churn need precise definitions (page 6).</li></ul>''', style="grid-column: span 2")}
  {card("Product page URLs first seen in the archive (new and renamed pages)", chart_launch)}
</div>"""
    title = (f"Every brand sells the same ladder: 6 units cost {pct(six)} less per unit than 1, "
             f"and {pct(six_sub)} less on subscription")
    subtitle = ("Prices, bundles and subscribe & save terms read from the live product pages; price history and launch pace "
                "from archived copies. One pricing logic across 6 stores is good news for a shared data model.")
    return page(2, "PUBLIC DATA", title, subtitle, body,
                f"Sources: storefront product pages (prices per unit, crossed-out list price) · Internet Archive CDX, monthly captures since 2023 · collected {SNAPSHOT}"), dict(six=six, six_sub=six_sub)


def page_demand(d):
    t = d.trends.pivot_table(index="month", columns="search_term", values="interest")
    t = t[t.index < "2026-11-01"]
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    styles = {"PureHealth Research": (BLUE, 2.4), "Nation Health MD": (DARK, 1.8), "Pureance": (LIGHT, 1.4),
              "Nature's Blast": (GREY, 1.4)}
    for term in t.columns:
        color, lw = styles.get(term, (LIGHTGREY, 1.0))
        ax.plot(t.index, t[term].rolling(3, min_periods=1).mean(), color=color, lw=lw, label=term)
    ax.set_ylabel("Google Trends interest, US (3-month avg)"); ax.legend(ncol=4, fontsize=8, loc="upper left")
    chart = svg(fig)

    weekly = pd.read_csv(sorted((ROOT / "data" / "raw" / "trends").glob("*.csv"))[-1], parse_dates=["week"]).set_index("week")
    share = (weekly > 0).mean().sort_values()
    fig, ax = plt.subplots(figsize=(3.8, 3.0))
    ax.barh(share.index, share.values * 100, color=[BLUE if v > 0.25 else LIGHTGREY for v in share.values])
    for i, v in enumerate(share.values):
        ax.text(v * 100 + 1, i, f"{v * 100:.0f}%", va="center", fontsize=8, color=SUB)
    ax.set_xlabel("% of weeks with measurable search interest"); ax.grid(axis="y", visible=False); ax.set_xlim(0, 60)
    chart_share = svg(fig)
    measurable = int((share > 0.25).sum())
    body = f"""
<div class="grid" style="grid-template-columns: 1.75fr 1fr; grid-template-rows: auto auto;">
  {card("Branded search interest over 5 years (relative index 0-100, one shared scale)", chart)}
  {card("Most brands rarely register in branded search", chart_share)}
  {card("Reading this page", '''<ul class="bullets">
     <li><b>What it shows</b>: relative interest, not volumes. Two batches of terms were put on one scale through a shared anchor (PureHealth Research).</li>
     <li><b>What it suggests</b>: demand for most brands is created by paid media, not found through branded search. The ad platform connectors, campaign naming and attribution are therefore the most business-critical pipelines.</li>
     <li><b>Limits</b>: low-volume terms show as zero; "PetMade" and "VitalPeak" also match unrelated searches; ad libraries were not collected (login required).</li></ul>''', style="grid-column: span 2")}
</div>"""
    title = (f"Only {measurable} of 7 brands show up in branded search most weeks: demand is bought through paid media, "
             "so ad data has to be right")
    subtitle = "Google Trends, United States, weekly over 5 years. A signal of where demand comes from, with clear limits."
    return page(3, "PUBLIC DATA", title, subtitle, body,
                f"Source: Google Trends (pytrends), US, 5 years, weekly, collected {SNAPSHOT}. Relative index; not search volumes.")


def page_mapping(d):
    o = d.offers
    examples = pd.DataFrame([
        ["PureHealth Research", "Liver Health Formula", "LHFU, quantity 1 / 3 / 6 (code per bottle)", "LHFU1AD / 3AD / 6AD (code per bundle)"],
        ["Nation Health MD", "ActiveSpan", "ATK, quantity 1 / 3 / 6", "ATK3AD · store code is LHP, not NHMD"],
        ["PetMade", "Calm Soft Dog Chews", "CFOF &amp; QUANTITY=3 (third link style)", "CFOF3AD, quantity 3"],
        ["Trumeta", "Bone Broth Protein", "TBPB1 x 3 but TBPB6B for 6 (two styles)", "TBPB3SS (SS suffix, not AD)"],
        ["Same name, two brands", "Bone Broth Protein", "PHR: TXM", "TRU: TBPB1 · two products, not one"],
        ["Same need, four brands", "Liver support", "PHR Liver Health Formula · NHMD Liver Renew", "NBL Liver 360 · VPK Liver Cleanse &amp; Detox"],
    ], columns=["Brand", "Product", "One-time store code(s)", "Subscription / other"])
    rules = pd.DataFrame([
        ["shop", "LHFU3AD", "PHR:liver-health-formula-supplement", "3", "0"],
        ["warehouse", "WH-PHR-10308", "PHR:liver-health-formula-supplement", "1", "0"],
        ["campaign rule", "token 'bloodsugar'", "PHR:blood-sugar-formula-supplement", "-", "0"],
        ["campaign rule", "token 'bloodsugr' (alias)", "PHR:blood-sugar-formula-supplement", "-", "1"],
        ["shop", "YCH1AD (new product)", "PHR:yeast-protein-creatine-electrolytes", "1", "1"],
        ["ad account", "act_...99777", "VPK", "-", "1"],
    ], columns=["Source", "Source code", "Canonical product / brand", "Units", "Fixed in v."])

    before_rev = d.q("select sum(case when is_mapped then allocated_revenue_usd end)/sum(allocated_revenue_usd) r from marts.fct_order_lines where order_date>='2026-07-01'", True).r[0]
    before_spend = d.q("select sum(case when product_key is not null then spend_usd end)/sum(spend_usd) r from marts.fct_ad_spend_daily where ad_date>='2026-05-01'", True).r[0]
    after_rev = d.q("select sum(case when is_mapped then allocated_revenue_usd end)/sum(allocated_revenue_usd) r from marts.fct_order_lines where order_date>='2026-07-01'").r[0]
    after_spend = d.q("select sum(case when product_key is not null then spend_usd end)/sum(spend_usd) r from marts.fct_ad_spend_daily where ad_date>='2026-05-01'").r[0]
    unmapped = d.q("select sum(allocated_revenue_usd) v, min(order_date) d from marts.fct_order_lines where not is_mapped", True)

    fig, ax = plt.subplots(figsize=(3.8, 2.5))
    x = np.arange(2)
    ax.bar(x - 0.18, [before_rev * 100, before_spend * 100], 0.34, color=RED, label="before fix (v0)")
    ax.bar(x + 0.18, [after_rev * 100, after_spend * 100], 0.34, color=BLUE, label="after fix (v1)")
    for xi, v in zip(list(x - 0.18) + list(x + 0.18), [before_rev, before_spend, after_rev, after_spend]):
        ax.text(xi, v * 100 + 1, f"{v * 100:.1f}%", ha="center", fontsize=8, color=SUB)
    ax.set_xticks(x); ax.set_xticklabels(["sales revenue mapped\nto a product (Jul-Sep 26)", "ad spend mapped\nto a product (May-Sep 26)"], fontsize=8)
    ax.set_ylim(60, 118); ax.legend(fontsize=8, loc="upper left", ncol=2); ax.grid(axis="x", visible=False)
    chart = svg(fig)

    n_codes = o.store_sku.nunique()
    n_products = d.q("select count(*) n from marts.dim_product").n[0]
    body = f"""
<div class="grid" style="grid-template-columns: 1.35fr 1fr; grid-template-rows: auto auto;">
  {card("Why mapping is hard: real codes and names from the public stores", table(examples, small=True))}
  {card("Mapping rate before and after the fix", chart + f"<p class='note'>Before the fix, {money(unmapped.v[0])} of sales from {unmapped.d[0]:%d %b %Y} had no product: the new product's SKUs were not in the mapping.</p>")}
  {card("The rules live in versioned seeds, not in the report (seeds/mapping/*.csv)", table(rules, small=True))}
  {card("Fix at the source, not in the chart", f'''<ol class="steps">
     <li><b>Alert</b> <code>assert_no_unmapped_sales</code> fails on the first sale of SKU <code>YCH1AD</code>.</li>
     <li><b>Fix</b>: one pull request adds the new codes to <code>product_mapping.csv</code> (fixed_in_version = 1), reviewed like code.</li>
     <li><b>Prevent</b>: the same test runs on every build, so the next launch is caught on day one. Campaign typos get an alias <i>and</i> are renamed in Ads Manager.</li></ol>
     <p class="note">{n_codes} real store codes and the 3PL codes map to {n_products} canonical products, key <code>brand_code:product_slug</code>.</p>''')}
</div>"""
    title = (f"Every sale and every ad dollar now maps to one of {n_products} products: "
             f"{pct(1 - before_rev, 1)} of recent sales were unmapped before the fix")
    subtitle = ("The public catalogue shows three SKU code styles, a store code that differs from the brand name and "
                "near-identical products across brands. Mapping rules are versioned seeds, tested on every build.")
    return page(4, "PUBLIC + SIMULATED", title, subtitle, body,
                f"Codes and products: public storefronts ({SNAPSHOT}). Sales, spend and mapping rates: SIMULATED (seed 42), before (fix_version 0) vs after (1).")


def page_warehouse(d):
    import json
    manifest = json.loads((DBT / "target" / "manifest.json").read_text(encoding="utf-8"))
    nodes = manifest["nodes"].values()
    models = [n for n in nodes if n["resource_type"] == "model"]
    tests = [n for n in nodes if n["resource_type"] == "test"]
    seeds = [n for n in nodes if n["resource_type"] == "seed"]
    by_layer = pd.Series([n["fqn"][1] for n in models]).value_counts()
    singular = sum(1 for t in tests if "test_metadata" not in t)
    flow = f"""
<div class="flow">
  <div class="layer"><div class="lh">Sources</div><div class="box">Store</div><div class="box">Subscriptions</div><div class="box">Payments</div><div class="box">3PL</div><div class="box">Meta · Google Ads</div><div class="box">CRM · Finance</div></div>
  <div class="arrow">→</div>
  <div class="layer"><div class="lh">raw</div><div class="box">11 tables<br/><span>as received</span></div><div class="box seed">seeds<br/><span>{len(seeds)} CSV: public catalogue, mapping rules, FX</span></div></div>
  <div class="arrow">→</div>
  <div class="layer"><div class="lh">staging · {by_layer.get('staging', 0)}</div><div class="box">1 model per source<br/><span>rename, types, UTC, cents→units, dedupe</span></div></div>
  <div class="arrow">→</div>
  <div class="layer"><div class="lh">intermediate · {by_layer.get('intermediate', 0)}</div><div class="box">product &amp; brand mapping</div><div class="box">subscription periods</div><div class="box">order ↔ payment match</div></div>
  <div class="arrow">→</div>
  <div class="layer"><div class="lh">marts · {by_layer.get('marts', 0)}</div><div class="box">dims: brand, product, customer, date, ad account</div><div class="box">facts: orders, lines, payments, ad spend, subs daily</div><div class="box blue">mart_media_buying · mart_finance_reconciliation · mart_subscription_health · mart_roas_bridge</div></div>
  <div class="arrow">→</div>
  <div class="layer"><div class="lh">BI</div><div class="box">Looker Studio</div><div class="box">Power BI</div></div>
</div>"""
    star = """
<div class="star">
  <div class="s dim">dim_date</div><div class="s dim">dim_brand</div><div class="s dim">dim_product</div>
  <div class="s fact">fct_orders · fct_order_lines<br/>fct_payments · fct_ad_spend_daily<br/>fct_subscriptions_daily</div>
  <div class="s dim">dim_customer</div><div class="s dim">dim_ad_account</div><div class="s dim">seeds: mapping</div>
</div>"""
    stats = f"""<div class="facts">
      <div><b>{len(models)}</b><span>dbt models (staging {by_layer.get('staging', 0)}, intermediate {by_layer.get('intermediate', 0)}, marts {by_layer.get('marts', 0)})</span></div>
      <div><b>{len(tests)}</b><span>tests: {len(tests) - singular} generic + {singular} business rules</span></div>
      <div><b>2</b><span>targets: DuckDB (built and tested here) and BigQuery (parsed; needs a Google account to run)</span></div>
      <div><b>0</b><span>engine-specific SQL outside 5 small dispatch macros</span></div></div>"""
    body = f"""
<div class="grid" style="grid-template-columns: 1fr 1fr; grid-template-rows: auto auto;">
  {card("Sources → raw → staging → intermediate → marts → dashboards", flow, style="grid-column: span 2")}
  {card("dbt lineage graph (dbt docs, generated from the project)", img_base64(DOCS / "img" / "dbt_lineage_raw.png", "width:100%;border-radius:6px"))}
  {card("Star schema and project in numbers", star + stats)}
</div>"""
    title = f"One dbt project, {len(models)} models and {len(tests)} tests: runs locally on DuckDB, written to run unchanged on BigQuery"
    subtitle = ("Each layer has one job: staging cleans each source, intermediate holds the business logic (mapping, "
                "subscription periods, payment matching), marts serve each team. Cross-database macros keep it portable.")
    return page(5, "SIMULATED", title, subtitle, body,
                "dbt Core 1.12 · dbt-duckdb · BigQuery-ready (profiles.example.yml) · Dataform version of 2 models in dataform/ · SIMULATED data"), dict(models=len(models), tests=len(tests))


def page_metrics(d):
    daily = d.q("""select date_day, sum(is_active::int) active, count(*) naive, sum(is_paused::int) paused, sum(is_past_due::int) past_due
                   from marts.fct_subscriptions_daily group by 1 order by 1""")
    daily["date_day"] = pd.to_datetime(daily.date_day)
    end = daily.iloc[-1]
    gap = end.naive / end.active - 1
    fig, ax = plt.subplots(figsize=(4.6, 2.7))
    ax.plot(daily.date_day, daily.naive, color=RED, lw=1.6, label="naive: tool status ACTIVE")
    ax.plot(daily.date_day, daily.active, color=BLUE, lw=2.2, label="documented: state = active")
    ax.fill_between(daily.date_day, daily.active, daily.naive, color=RED, alpha=0.12)
    ax.set_ylabel("subscriptions"); ax.legend(fontsize=8, loc="upper left"); ax.tick_params(axis="x", labelsize=8)
    chart_gap = svg(fig)

    churn = d.q("""select month_start, sum(voluntary_cancellations) vol, sum(involuntary_cancellations) inv, sum(base_start) base
                   from marts.mart_subscription_health group by 1 order by 1""")
    churn = churn[pd.to_datetime(churn.month_start) >= "2025-03-01"]
    fig, ax = plt.subplots(figsize=(4.2, 2.7))
    labels = pd.to_datetime(churn.month_start).dt.strftime("%b %y")
    ax.bar(labels, churn.vol / churn.base * 100, color=BLUE, label="voluntary")
    ax.bar(labels, churn.inv / churn.base * 100, bottom=churn.vol / churn.base * 100, color=LIGHT, label="involuntary (payment failed)")
    ax.set_ylabel("monthly churn rate, %"); ax.legend(fontsize=8); ax.grid(axis="x", visible=False)
    ax.tick_params(axis="x", labelsize=7, rotation=90)
    chart_churn = svg(fig)
    avg_churn = (churn.vol.sum() + churn.inv.sum()) / churn.base.sum()
    inv_share = churn.inv.sum() / (churn.vol.sum() + churn.inv.sum())

    defs = pd.DataFrame([
        ["active_subscription", "state = active on that day: not paused, no failed payment being retried, not cancelled"],
        ["active_customer", "≥ 1 order with positive net revenue in the last 365 days, or an active subscription"],
        ["churned_subscription", "a cancelled event in the period; voluntary and involuntary split; reactivation counted apart"],
        ["churn_rate", "cancellations in month ÷ base at month start (active + paused + past due)"],
        ["net_revenue", "order total after discount − refunds − chargebacks known today, on the order month"],
        ["CPA · ROAS · MER", "spend ÷ first-party orders · first-party revenue ÷ spend · total net revenue ÷ total spend"],
    ], columns=["Metric", "Definition (METRICS.md, with SQL)"])
    active_customers = d.q("""with b as (select distinct customer_id from marts.fct_orders where net_revenue_usd > 0
                                 and order_date > date '2026-09-30' - interval 365 day and order_date <= date '2026-09-30'),
                             s as (select distinct customer_id from marts.fct_subscriptions_daily
                                 where date_day = date '2026-09-30' and is_active)
                             select count(*) n from (select customer_id from b union select customer_id from s)""").n[0]
    sql = """<pre>select date_day, count(*) as active_subscriptions
from marts.fct_subscriptions_daily
where is_active          -- state = 'active'
group by date_day</pre>"""
    body = f"""
<div class="grid" style="grid-template-columns: 1.15fr 1fr 1fr; grid-template-rows: auto auto;">
  {card("One definition per metric, written once", table(defs, small=True) + f"<div class='facts' style='margin-top:14px'><div><b>{int(end.active):,}</b><span>active subscriptions, 30 Sep 2026</span></div><div><b>{active_customers:,}</b><span>active customers (365 days or subscribed)</span></div><div><b>{pct(avg_churn, 1)}</b><span>average monthly churn, Mar 25 - Sep 26</span></div><div><b>{pct(inv_share)}</b><span>of cancellations are failed payments</span></div></div>", style="grid-row: span 2")}
  {card("Naive vs documented active subscriptions", chart_gap)}
  {card("Churn rate by month (cancellations ÷ base at start)", chart_churn)}
  {card("Edge cases decided, not left to each chart", f'''<ul class="bullets">
     <li><b>Paused</b>: not active, stays in the churn base.</li>
     <li><b>Payment failed</b>: "past due" while retries run; active again if a retry succeeds, otherwise involuntary churn ({pct(inv_share)} of all cancellations).</li>
     <li><b>Reactivated</b>: active again from that day; its earlier cancellation still counts as churn.</li></ul>''')}
  {card("The SQL behind the number", sql)}
</div>"""
    title = (f"Counting the subscription tool's ACTIVE status overstates active subscriptions by {pct(gap, 1)}: "
             "paused and failing ones are not active")
    subtitle = (f"On {end.date_day:%d %b %Y}: {int(end.naive):,} naive vs {int(end.active):,} documented "
                f"({int(end.paused):,} paused, {int(end.past_due):,} past due). Average monthly churn {pct(avg_churn, 1)}.")
    return page(6, "SIMULATED", title, subtitle, body, "SIMULATED subscriptions (seed 42), definitions in METRICS.md · metric logic in fct_subscriptions_daily and mart_subscription_health"), dict(gap=gap)


def page_trace(d):
    month = "2026-05-01"
    b = d.q(f"select * from marts.mart_roas_bridge where month_start = '{month}'").iloc[0]
    b0 = d.q(f"select * from marts.mart_roas_bridge where month_start = '{month}'", True).iloc[0]
    raw_dupes = d.q("""select sum(cast(spend as double)) s from '../data/simulated/raw_meta_ads.parquet'
                       where _load_batch = 'resync'""").s[0]
    tz = d.q("""select avg(case when la_date <> ny_date then 1 else 0 end) share from (
                  select cast(timezone('America/Los_Angeles', timezone('UTC', o.created_at_utc)) as date) la_date, o.order_date ny_date
                  from marts.fct_orders o where o.attributed_platform = 'google')""").share[0]

    steps = [("Platform\nvalue", b.platform_reported_value_usd, "total"),
             ("Attribution\nwindows", -b.step_attribution_window_usd, "step"),
             ("Time\nzone", -b.step_time_zone_usd, "step"),
             ("Refunds &\nchargebacks", -b.step_refunds_chargebacks_usd, "step"),
             ("Net revenue,\npaid orders", b.paid_net_usd, "total")]
    fig, ax = plt.subplots(figsize=(6.6, 3.1))
    running = 0
    for i, (label, value, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, value / 1e3, color=BLUE if i == 0 else DARK)
            running = value
            ax.text(i, value / 1e3 + 8, money(value), ha="center", fontsize=9, color=TEXT, fontweight="bold")
        else:
            ax.bar(i, value / 1e3, bottom=running / 1e3, color=RED)
            ax.text(i, running / 1e3 + 8, "−" + money(abs(value)), ha="center", fontsize=9, color=RED)
            running += value
    ax.set_xticks(range(len(steps))); ax.set_xticklabels([s[0] for s in steps], fontsize=8)
    ax.set_ylabel("USD thousands, May 2026"); ax.grid(axis="x", visible=False)
    ax.axhline(b.warehouse_spend_usd / 1e3, color=GREY, ls="--", lw=1)
    ax.text(4.45, b.warehouse_spend_usd / 1e3 + 8, f"ad spend {money(b.warehouse_spend_usd)}", ha="right", fontsize=8, color=GREY)
    chart = svg(fig)

    layers = pd.DataFrame([
        ["1 · Ad platform UI", f"{money(b.platform_reported_value_usd)} value, {int(b.platform_conversions):,} conversions", "Platform counts view-through and 7-day clicks"],
        ["2 · Raw connector tables", f"spend +{money(raw_dupes)} if read as is", "14 May loaded twice (re-sync); new account missing 5 days"],
        ["3 · Staging", f"spend {money(b0.warehouse_spend_usd)} → {money(b.warehouse_spend_usd)} after backfill", f"dedupe latest load; invoice {money(b.billed_spend_usd)} matches"],
        ["4 · Intermediate / marts", f"{int(b.paid_orders):,} real paid orders, {money(b.paid_gross_usd)} gross", "Orders joined on the campaign id in the UTM"],
        ["5 · Chart (Finance)", f"{money(b.paid_net_usd)} net", "After refunds and chargebacks; NY business day"],
    ], columns=["Layer", "What the number is", "What changes it"])
    body = f"""
<div class="grid" style="grid-template-columns: 1.25fr 1fr; grid-template-rows: auto auto;">
  {card("Revenue bridge for paid campaigns, May 2026 (mart_roas_bridge)", chart)}
  {card("The question", f'''<p class="lead">Media Buying: <b>"ROAS is {b.roas_platform:.2f}."</b><br/>Finance: <b>"ROAS is {b.roas_first_party_net:.2f}."</b></p>
     <p>Both are right about different numbers. Walking the number down each layer:</p>
     <ul class="bullets"><li><b>{pct(b.step_attribution_window_usd / b.platform_reported_value_usd)}</b> of platform value is not backed by a real order (attribution windows).</li>
     <li>The time zone moves little over a month but <b>{pct(tz)}</b> of Google-attributed orders change day between LA and NY: it matters for daily pacing.</li>
     <li>Refunds and chargebacks take another <b>{pct(b.step_refunds_chargebacks_usd / b.paid_gross_usd, 1)}</b>.</li>
     <li>Before the fixes, spend was <b>{money(b.billed_spend_usd - b0.warehouse_spend_usd)}</b> short of the invoice (new account) and would have been <b>{money(raw_dupes)}</b> too high from the duplicate load.</li></ul>''')}
  {card("Trace across every layer", table(layers, small=True), style="grid-column: span 2")}
</div>"""
    title = (f"Media Buying's ROAS of {b.roas_platform:.2f} and Finance's {b.roas_first_party_net:.2f} are both right: "
             f"attribution windows explain most of the gap")
    subtitle = ("An investigation from the ad platform down to the chart, with every difference quantified. The agreed numbers "
                f"for May 2026: first-party ROAS {b.roas_first_party_gross:.2f} gross, {b.roas_first_party_net:.2f} net, MER {b.mer:.2f}.")
    return page(7, "SIMULATED", title, subtitle, body,
                "SIMULATED data (seed 42) · mart_roas_bridge, mart_media_buying, raw_meta_ads, before-fix replay (fix_version 0)"), dict(roas_platform=b.roas_platform, roas_net=b.roas_first_party_net)


def page_quality(d):
    det = d.detection
    detectable = det[det.outcome != "structural - explained in reconciliation bridge"]
    caught = int((detectable.outcome == "detected").sum())
    rows = det.copy()
    rows["Outcome"] = rows.outcome.map({"detected": "detected", "missed": "missed",
                                        "structural - explained in reconciliation bridge": "explained (bridge)"})
    rows["Caught by"] = rows.caught_by.fillna("").str.replace("assert_", "").str.replace(", ", "<br/>")
    short = {
        1: "Typo in campaign name", 2: "Wrong brand in campaign name", 3: "Name matches the wrong product",
        4: "Dispute wave on a closed month", 5: "PayPal import in units, not cents", 6: "EUR/GBP, cents vs units",
        7: "Webhook replays (485 orders)", 8: "Paused/failing counted active", 9: "Platform conversions > orders",
        10: "Time zones (NY / LA / Vilnius / UTC)", 11: "Connector loaded a day twice", 12: "New ad account missing 5 days",
        13: "New product without mapping"}
    rows["Injected issue"] = rows.issue_id.map(short)
    rows = rows.sort_values(["issue_type", "issue_id"])
    tbl = table(rows[["issue_type", "Injected issue", "Outcome", "Caught by"]].rename(columns={"issue_type": "#"}),
                highlight_col=("Outcome", lambda v: v == "missed"), small=True)

    alert = (DOCS / "alerts_example.md").read_text(encoding="utf-8")
    alert_lines = [line for line in alert.splitlines() if line.startswith("- **")][:7]
    alert_html = "".join(f"<li>{escape(line[2:].replace('**', '')).split(' · next step')[0]}</li>" for line in alert_lines)
    tests = d.q("select 1").shape  # placeholder to keep the connection warm
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    ax.barh(["missed", "detected"], [len(detectable) - caught, caught], color=[RED, BLUE], height=0.55)
    for i, v in enumerate([len(detectable) - caught, caught]):
        ax.text(v + 0.15, i, str(v), va="center", fontsize=10, color=TEXT)
    ax.set_xlim(0, len(detectable) + 1.5); ax.grid(axis="y", visible=False); ax.set_xlabel("injected data defects")
    chart = svg(fig)
    body = f"""
<div class="grid" style="grid-template-columns: 1.3fr 1fr; grid-template-rows: auto auto;">
  {card("Every injected problem and what caught it (answer key never read by the tests)", tbl, style="grid-row: span 2")}
  {card("Detection rate on data defects", chart + f"<p class='note'>The miss: a campaign named 'Sleep_StressRelief' matches the Sleep Formula rule and is silently attributed to it. Next test to add: flag campaign names that match more than one product rule.</p>")}
  {card("The nightly alert (docs/alerts_example.md, from run_results.json)", f"<div class='slack'><div class='slack-h'>Data quality alert - 7 failing · 5 warnings</div><ul>{alert_html}</ul><div class='slack-f'>+ source freshness: raw_shop_orders STALE (extract ends 30 Sep)</div></div>")}
</div>"""
    title = (f"The tests caught {caught} of {len(detectable)} injected data defects before any dashboard showed them; "
             "the miss is documented, not hidden")
    subtitle = ("Problems were injected on purpose and listed in a hidden answer key. The warehouse was replayed without the "
                "fixes (fix_version 0); a defect counts as caught only if its id appears in a failing test's stored rows.")
    return page(8, "SIMULATED", title, subtitle, body,
                "SIMULATED data (seed 42) · dbt tests with store_failures · src/evaluate_detection.py · src/alerts.py"), dict(caught=caught, detectable=len(detectable))


def page_reporting(d):
    mb = d.q("""select brand_code, sum(spend_usd) spend, sum(first_party_orders) orders,
                       sum(first_party_gross_revenue_usd) rev, sum(platform_conversion_value_usd) pv
                from marts.mart_media_buying where ad_month >= '2026-07-01' group by 1""").set_index("brand_code").reindex(BRAND_ORDER)
    fig, ax = plt.subplots(figsize=(4.1, 2.6))
    x = np.arange(len(mb))
    ax.bar(x - 0.2, mb.pv / mb.spend, 0.38, color=LIGHTGREY, label="platform ROAS")
    ax.bar(x + 0.2, mb.rev / mb.spend, 0.38, color=BLUE, label="first-party ROAS")
    ax.axhline(1, color=GREY, ls="--", lw=1)
    ax.set_xticks(x); ax.set_xticklabels(mb.index, fontsize=8); ax.legend(fontsize=8); ax.grid(axis="x", visible=False)
    ax.set_ylabel("ROAS, Jul-Sep 2026")
    chart_mb = svg(fig)
    cpa = pd.DataFrame({"Brand": mb.index, "Spend": [money(v) for v in mb.spend], "CPA": [f"${v:.0f}" for v in mb.spend / mb.orders],
                        "ROAS": [f"{v:.2f}" for v in mb.rev / mb.spend]})

    fin = d.q("""select month_start, sum(gross_revenue_usd) sales, sum(charges_usd) charges, sum(refunds_usd + chargebacks_usd) refunds,
                        sum(refunds_on_earlier_months_usd) earlier, sum(net_cash_revenue_usd) net_cash, sum(ad_spend_usd) spend
                 from marts.mart_finance_reconciliation group by 1 order by 1""")
    fin["month_start"] = pd.to_datetime(fin.month_start)
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    ax.bar(fin.month_start, fin.net_cash / 1e3, width=20, color=BLUE, label="net cash revenue")
    ax.bar(fin.month_start, -fin.refunds / 1e3, width=20, color=RED, label="refunds + chargebacks")
    ax.plot(fin.month_start, fin.net_cash / fin.spend * 100, color=DARK, lw=0)  # keeps axis range simple
    ax.set_ylabel("USD thousands"); ax.legend(fontsize=8, loc="upper left"); ax.tick_params(axis="x", labelsize=7)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %y")); ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(interval=3))
    chart_fin = svg(fig)
    recon = fin.tail(3).assign(Month=lambda f: f.month_start.dt.strftime("%b %Y"))
    recon_tbl = pd.DataFrame({"Month": recon.Month, "Shop sales": [money(v) for v in recon.sales],
                              "PSP charges": [money(v) for v in recon.charges],
                              "Gap": [money(abs(c - s)) if abs(c - s) >= 1 else "$0" for s, c in zip(recon.sales, recon.charges)],
                              "On earlier months": [money(v) for v in recon.earlier]})

    sub = d.q("""select brand_code, sum(active_end) active, sum(naive_active_end) naive, sum(cancellations) c, sum(base_start) base
                 from marts.mart_subscription_health where month_start = '2026-09-01' group by 1""").set_index("brand_code").reindex(BRAND_ORDER).fillna(0)
    fig, ax = plt.subplots(figsize=(4.1, 2.6))
    ax.barh(sub.index, sub.naive, color=PALE, label="tool ACTIVE (naive)")
    ax.barh(sub.index, sub.active, color=BLUE, label="active (documented)", height=0.5)
    ax.invert_yaxis(); ax.legend(fontsize=8, loc="lower right"); ax.grid(axis="y", visible=False)
    ax.set_xlabel("subscriptions, 30 Sep 2026")
    chart_ops = svg(fig)
    churn_tbl = pd.DataFrame({"Brand": sub.index, "Active": [f"{int(v):,}" for v in sub.active],
                              "Churn Sep": [pct(c / b, 1) if b else "-" for c, b in zip(sub.c, sub.base)]})
    body = f"""
<div class="grid three">
  <div class="col"><div class="col-h">Media Buying</div>{card("Platform vs first-party ROAS by brand", chart_mb)}{card("", table(cpa, {"Spend": "right", "CPA": "right", "ROAS": "right"}, small=True))}</div>
  <div class="col"><div class="col-h">Finance</div>{card("Net cash revenue and refunds by month", chart_fin)}{card("", table(recon_tbl, {"Shop sales": "right", "PSP charges": "right", "Gap": "right", "On earlier months": "right"}, small=True))}</div>
  <div class="col"><div class="col-h">Operations</div>{card("Active subscriptions by brand", chart_ops)}{card("", table(churn_tbl, {"Active": "right", "Churn Sep": "right"}, small=True))}</div>
</div>"""
    title = "Three teams, three views, one set of definitions: every number on these pages comes from the same marts"
    subtitle = ("Mini versions of the Looker Studio pages (sources = the 3 reporting marts; ratios as calculated fields "
                "from summed columns). Same model works in Power BI.")
    return page(9, "SIMULATED", title, subtitle, body,
                "SIMULATED data (seed 42) · mart_media_buying, mart_finance_reconciliation, mart_subscription_health")


def page_methods(d, facts):
    body = f"""
<div class="grid" style="grid-template-columns: 1fr 1fr 1fr;">
  {card("Data", '''<ul class="bullets">
     <li><b>PUBLIC</b>: 7 storefronts (sitemap → product pages, 1 snapshot, 2.5 s between requests, robots.txt respected), Wayback Machine CDX, Google Trends, company press release and careers page. Sources and dates: <code>data/SOURCES.md</code>.</li>
     <li><b>SIMULATED</b>: 21 months of orders, subscriptions, payments, shipments, ad delivery, invoices and CRM contacts, built on the real catalogue (<code>src/simulate.py</code>, seed 42). Assumptions: <code>data/ASSUMPTIONS.md</code>.</li>
     <li>Skipped: Trustpilot (robots.txt disallows crawlers), ad libraries (login), company registry (no clear match).</li></ul>''')}
  {card("Methods", '''<ul class="bullets">
     <li><b>dbt</b>: staging per source, intermediate business logic, marts per team; seeds for public catalogue and versioned mapping rules; 5 adapter-dispatch macros for DuckDB/BigQuery.</li>
     <li><b>Tests</b>: generic (unique, not null, relationships, accepted values) + 12 business rules with stored failures; source freshness.</li>
     <li><b>Detection</b>: warehouse replayed without fixes (<code>--vars '{fix_version: 0}'</code>), failing rows matched to a hidden answer key.</li>
     <li><b>Report</b>: Python + matplotlib → HTML → PDF (headless Edge).</li></ul>''')}
  {card("Limits", '''<ul class="bullets">
     <li>Simulated data shows methods, not Impact Brands' performance, volumes or systems.</li>
     <li>VitalPeak shows no price online: assumed price ladder in the simulation.</li>
     <li>Archive first-capture dates approximate launches; Trends is a relative index.</li>
     <li>Categories come from product names: reporting labels, not health claims.</li>
     <li>Dataform models are written for comparison, not run here.</li></ul>''')}
  {card("Reproduce", '''<pre>pip install -r requirements.txt
python src/collect_storefronts.py   # optional: new snapshot
python src/build_public.py
python src/simulate.py
cd dbt && cp profiles.example.yml profiles.yml
dbt build --profiles-dir .                    # with fixes
dbt run --profiles-dir . --target duckdb_before_fix --vars "{fix_version: 0}"
dbt test --profiles-dir . --target duckdb_before_fix \
  --vars "{fix_version: 0}" --target-path target_before_fix
cd .. && python src/evaluate_detection.py
python src/alerts.py --target-path dbt/target_before_fix \
  --db dbt/impact_brands_before_fix.duckdb
python src/build_report.py</pre>''', style="grid-column: span 2")}
  {card("AI note", f"<p class='lead' style='font-size:13px'>{AI_NOTE}</p>")}
</div>"""
    return page(10, "", "Methods, limits and how to reproduce every number", "Everything in this report is regenerated from code in the repository.", body,
                f"Public data collected {SNAPSHOT} · simulated data seed 42")


def page_overview(d, f):
    body = f"""
<div class="kpis">
  {kpi("PUBLIC · page 1", str(f['total']), "products across 7 storefronts, all sold through one offer logic", "")}
  {kpi("PUBLIC + SIMULATED · page 4", "100%", "of sales and ad spend mapped to a product after the fix at the source", "")}
  {kpi("SIMULATED · page 7", f"{f['roas_platform']:.2f} vs {f['roas_net']:.2f}", "platform ROAS vs net first-party ROAS: the gap, explained layer by layer", "")}
  {kpi("SIMULATED · page 8", f"{f['caught']} of {f['detectable']}", "injected data defects caught by dbt tests before a dashboard showed them", "")}
</div>
<div class="grid" style="grid-template-columns: 1.1fr 1fr; margin-top: 14px; height: auto;">
  {card("<span class='big'>Business questions</span>", '''<ol class="questions">
     <li><b>Portfolio</b> What do the 7 brands sell, and how alike are they? <span>p.1-3</span></li>
     <li><b>Mapping</b> Can every SKU, campaign and ad account be tied to one product and brand? <span>p.4</span></li>
     <li><b>Warehouse &amp; metrics</b> What does a trusted model and metric layer look like? <span>p.5-6</span></li>
     <li><b>Reconciliation</b> Why do Media Buying and Finance see different ROAS? <span>p.7</span></li>
     <li><b>Quality &amp; reporting</b> Do the tests catch problems before users do? <span>p.8-9</span></li></ol>
     <p class="reco"><b>Recommendation:</b> keep product, brand and ad-account mapping in versioned seeds tested on every build, so a new
     product or account fails loudly on day one; report ROAS on first-party orders next to platform ROAS and MER; publish one definition of
     active subscription, active customer and churn, and build every dashboard on the same marts.</p>''')}
  {card("<span class='big'>Data &amp; methods</span>", '''<p><span class='lbl'>PUBLIC</span> real catalogue of the 7 storefronts (products, bundles, subscribe &amp; save prices, store SKU codes), archive history, Google Trends, company facts.</p>
     <p><span class='lbl'>SIMULATED</span> orders, subscriptions, payments, 3PL, Meta and Google Ads, CRM: generated on top of the real catalogue, with 13 problems injected on purpose. Not Impact Brands data.</p>
     <p><span class='lbl'>dbt</span> staging → intermediate → marts, versioned mapping seeds, generic + business-rule tests, alerts.</p>
     <p><span class='lbl'>Stack</span> DuckDB locally, same project on BigQuery; Looker Studio / Power BI on the reporting marts; Dataform version of 2 models.</p>''')}
</div>
{card("How to read this report", "<p><b>Titles</b> state the conclusion. <b>Tags</b> PUBLIC DATA / SIMULATED / PUBLIC + SIMULATED mark where the data comes from. <b>Red</b> marks gaps and alerts, <b>dashed lines</b> thresholds. <b>Code</b>: every number is rebuilt by the scripts and the dbt project in the repository.</p>", style="margin-top:14px")}
"""
    return page(0, "OVERVIEW", "Impact Brands: one trusted data model for 7 brands",
                "From public storefront data to a tested marketing &amp; subscription warehouse (dbt · BigQuery-ready · Looker Studio)",
                body, "Data sources listed in data/SOURCES.md")


CSS = """
@page { size: 1280px 720px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1280px; height: 720px; padding: 26px 34px 0 34px; background: #F4F4F2; page-break-after: always;
        display: flex; flex-direction: column; overflow: hidden; position: relative; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
h1 { font-size: 22px; font-weight: 700; margin: 0 0 4px 0; line-height: 1.2; max-width: 1060px; }
.subtitle { color: #52514E; font-size: 12.5px; margin: 0 0 12px 0; max-width: 1060px; }
.tag { font-size: 10.5px; font-weight: 700; letter-spacing: .06em; color: #52514E; border: 1px solid #C9C7C0;
       border-radius: 4px; padding: 3px 8px; white-space: nowrap; margin-top: 4px; }
main { flex: 1; min-height: 0; }
footer { display: flex; gap: 18px; font-size: 9px; color: #898781; padding: 6px 0 10px 0; }
footer .num { margin-left: auto; }
.grid { display: grid; gap: 12px; height: 100%; }
.grid.three { grid-template-columns: 1fr 1fr 1fr; }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 10px 12px; overflow: hidden; }
.card-title { font-size: 11.5px; font-weight: 600; margin-bottom: 6px; color: #0B0B0B; }
.card-body svg { width: 100%; height: auto; max-height: 245px; }
.card-body { font-size: 11px; color: #52514E; }
table { border-collapse: collapse; width: 100%; font-size: 10.5px; }
table.small { font-size: 9.6px; }
th { color: #898781; font-weight: 600; border-bottom: 1px solid #C9C7C0; padding: 3px 5px; }
td { padding: 3px 5px; border-bottom: 1px solid #EEEDE8; color: #0B0B0B; vertical-align: top; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 12px 16px; height: 128px; }
.kpi-label { font-size: 10px; font-weight: 700; letter-spacing: .04em; color: #52514E; }
.kpi-value { font-size: 36px; font-weight: 700; margin: 4px 0 2px 0; }
.kpi-note { font-size: 11.5px; color: #52514E; }
.big { font-size: 17px; font-weight: 700; }
ol.questions { padding-left: 18px; margin: 4px 0; font-size: 12.5px; color: #0B0B0B; }
ol.questions li { margin-bottom: 4px; } ol.questions b { color: #2A78D6; margin-right: 6px; }
ol.questions span { color: #898781; font-size: 10px; margin-left: 4px; }
.reco { font-size: 12px; color: #52514E; margin: 8px 0 0 0; } .reco b { color: #0B0B0B; }
.lbl { font-weight: 700; color: #52514E; font-size: 10.5px; margin-right: 6px; }
.card-body p { margin: 4px 0; font-size: 11.5px; }
ul.bullets, ol.steps { padding-left: 16px; margin: 2px 0; font-size: 11px; }
ul.bullets li, ol.steps li { margin-bottom: 4px; }
.note { font-size: 10px !important; color: #898781; }
.lead { font-size: 15px; color: #0B0B0B; }
code { font-family: Consolas, monospace; font-size: 10px; background: #F0EFEA; padding: 0 3px; border-radius: 3px; }
pre { font-family: Consolas, monospace; font-size: 10px; background: #F0EFEA; padding: 8px; border-radius: 6px; margin: 0; color: #0B0B0B; }
.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; margin-top: 6px; }
.facts div { display: flex; flex-direction: column; } .facts b { font-size: 22px; color: #0B0B0B; }
.facts span { font-size: 10.5px; color: #52514E; }
.flow { display: flex; align-items: stretch; gap: 6px; }
.layer { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.lh { font-size: 10px; font-weight: 700; color: #52514E; text-transform: uppercase; letter-spacing: .04em; }
.box { background: #F4F4F2; border: 1px solid #E1E0D9; border-radius: 6px; padding: 4px 6px; font-size: 10px; color: #0B0B0B; }
.box span { color: #898781; font-size: 9px; } .box.seed { border-style: dashed; } .box.blue { background: #CDE2FB; border-color: #86B6EF; }
.arrow { align-self: center; color: #898781; font-size: 18px; }
.star { display: grid; grid-template-columns: 1fr 1.5fr 1fr; gap: 6px; align-items: center; margin-bottom: 8px; }
.s { border-radius: 6px; padding: 5px; font-size: 10px; text-align: center; }
.s.dim { background: #F4F4F2; border: 1px solid #E1E0D9; } .s.fact { grid-row: span 3; grid-column: 2; background: #CDE2FB; border: 1px solid #86B6EF; font-weight: 600; }
.star .s:nth-child(1) { grid-column: 1; } .star .s:nth-child(2) { grid-column: 1; } .star .s:nth-child(3) { grid-column: 1; }
.star .s:nth-child(5), .star .s:nth-child(6), .star .s:nth-child(7) { grid-column: 3; }
.star .s:nth-child(4) { grid-row: 1 / span 3; }
.col { display: flex; flex-direction: column; gap: 8px; } .col-h { font-size: 13px; font-weight: 700; color: #2A78D6; }
.slack { border-left: 4px solid #D03B3B; padding: 4px 10px; background: #FFF; }
.slack-h { font-weight: 700; color: #0B0B0B; font-size: 11px; } .slack ul { padding-left: 14px; margin: 4px 0; font-size: 10px; color: #0B0B0B; }
.slack-f { font-size: 9.5px; color: #898781; }
"""


def find_browser():
    for candidate in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                      shutil.which("msedge") or "", shutil.which("google-chrome") or "", shutil.which("chromium") or ""]:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Edge or Chrome is needed to print the PDF")


def main():
    d = Data()
    p1, f1 = page_portfolio(d)
    p2, _ = page_pricing(d)
    p3 = page_demand(d)
    p4 = page_mapping(d)
    p5, _ = page_warehouse(d)
    p6, _ = page_metrics(d)
    p7, f7 = page_trace(d)
    p8, f8 = page_quality(d)
    p9 = page_reporting(d)
    facts = {**f1, **f7, **f8}
    pages = [page_overview(d, facts), p1, p2, p3, p4, p5, p6, p7, p8, p9, page_methods(d, facts)]
    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Impact Brands data case study</title><style>{CSS}</style></head><body>{''.join(pages)}</body></html>"
    out_html = DOCS / "report.html"
    out_html.write_text(html, encoding="utf-8")

    browser = find_browser()
    pdf = DOCS / "ImpactBrands_DataCaseStudy.pdf"
    profile = ROOT / ".browser_profile"
    if pdf.exists():
        pdf.unlink()
    subprocess.run([browser, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", out_html.as_uri()], check=True, timeout=180)
    # Edge can hand the job to a background process: wait until the PDF is fully written
    import time
    for _ in range(120):
        if pdf.exists() and pdf.stat().st_size > 0:
            time.sleep(2)
            break
        time.sleep(1)
    shutil.rmtree(profile, ignore_errors=True)
    print(f"written {pdf} ({pdf.stat().st_size / 1e6:.1f} MB)")

    # PNG of every page for the README
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(pdf))
    for index in range(len(document)):
        document[index].render(scale=1.5).to_pil().save(DOCS / "img" / f"page_{index:02d}.png")
    document.close()


if __name__ == "__main__":
    main()
