"""Turn dbt test results into a short, readable alert (like a Slack message).

Reads:
  - run_results.json written by `dbt test` / `dbt build`
  - sources.json written by `dbt source freshness` (optional)
  - the failing rows dbt stored in the `audit` schema (store_failures: true)
Writes a Markdown message (default docs/alerts_example.md).

Usage (from the repository root):
  python src/alerts.py --target-path dbt/target_before_fix --db dbt/impact_brands_before_fix.duckdb
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

# Plain-language explanation and owner of every custom test
EXPLAIN = {
    "assert_no_unmapped_sales": ("Sales on a store SKU with no product mapping", "Data", "add the SKU to seeds/mapping/product_mapping.csv"),
    "assert_no_unmapped_warehouse_skus": ("Warehouse item code with no product mapping", "Data / Ops", "add the 3PL code to the mapping seed"),
    "assert_no_unmapped_ad_accounts": ("Ad account sending spend without a brand", "Data / Media Buying", "add the account to seeds/mapping/ad_accounts.csv"),
    "assert_no_unmapped_campaigns": ("Campaign with spend that matches no product", "Media Buying", "fix the campaign name, or add a rule"),
    "assert_campaign_brand_matches_account": ("Campaign name says another brand than its ad account", "Media Buying", "rename the campaign at the source"),
    "assert_ad_spend_vs_platform_within_tolerance": ("Warehouse spend differs from the platform invoice", "Data", "check connector gaps, run a backfill"),
    "assert_orders_vs_payments_reconcile": ("Orders whose charge does not match the order total", "Finance / Payments", "check the payment import"),
    "assert_no_duplicate_order_events": ("Orders delivered twice by the shop webhook", "Data", "handled in staging; monitor the volume"),
    "assert_no_duplicate_ad_rows": ("Ad connector loaded a day twice", "Data", "handled in staging; check the connector sync log"),
    "assert_closed_month_revenue_stable": ("A closed month's revenue moved more than usual", "Finance", "review late refunds and chargebacks"),
    "assert_active_subscriptions_exclude_paused_and_failed": ("Active subscription count includes paused or failing ones", "Data", "use the documented definition"),
    "assert_subscription_status_matches_events": ("Subscription tool shows ACTIVE for paused or failing subscriptions", "Ops", "known tool behaviour; use the event history"),
}


def load_results(target_path):
    data = json.loads((target_path / "run_results.json").read_text(encoding="utf-8"))
    rows = []
    for result in data["results"]:
        if not result["unique_id"].startswith("test."):
            continue
        name = result["unique_id"].split(".")[2]
        rows.append({
            "test": name,
            "status": result["status"],            # pass / warn / fail / error
            "failures": result.get("failures") or 0,
            "relation": result.get("relation_name"),
        })
    return rows


def sample_rows(con, relation, limit=3):
    if not relation:
        return []
    try:
        frame = con.sql(f"select * from {relation} limit {limit}").df()
    except duckdb.Error:
        return []
    return frame.astype(str).to_dict("records")


def freshness(target_path):
    file = target_path / "sources.json"
    if not file.exists():
        return []
    data = json.loads(file.read_text(encoding="utf-8"))
    return [{"source": r["unique_id"].split(".", 2)[2], "status": r["status"],
             "max_loaded_at": r.get("max_loaded_at", "")[:10]} for r in data["results"]]


def build_message(results, con, fresh, title):
    failed = [r for r in results if r["status"] in ("fail", "error")]
    warned = [r for r in results if r["status"] == "warn"]
    passed = [r for r in results if r["status"] == "pass"]
    lines = [f"### :rotating_light: {title}",
             f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · {len(results)} tests · "
             f"{len(failed)} failing · {len(warned)} warnings · {len(passed)} passing_", ""]
    for label, group in (("Failing (blocks the reports)", failed), ("Warnings (known source issues, handled)", warned)):
        if not group:
            continue
        lines.append(f"**{label}**")
        for r in sorted(group, key=lambda r: -r["failures"]):
            what, owner, action = EXPLAIN.get(r["test"], (r["test"], "Data", "investigate"))
            lines.append(f"- **{what}**: {r['failures']:,} row(s) · owner: {owner} · next step: {action}  ")
            lines.append(f"  `{r['test']}`")
            for row in sample_rows(con, r["relation"], 2):
                preview = ", ".join(f"{k}={v}" for k, v in list(row.items())[:4])
                lines.append(f"  > {preview}")
        lines.append("")
    if fresh:
        lines.append("**Source freshness**")
        for f in fresh:
            icon = {"pass": "OK", "warn": "late", "error": "STALE"}.get(f["status"], f["status"])
            lines.append(f"- {f['source']}: {icon} (last load {f['max_loaded_at']})")
        lines.append("")
    lines.append("_Generated by src/alerts.py from dbt run_results.json. SIMULATED data._")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-path", default="dbt/target")
    parser.add_argument("--db", default="dbt/impact_brands.duckdb")
    parser.add_argument("--title", default="Data quality alert - warehouse run")
    parser.add_argument("--out", default="docs/alerts_example.md")
    args = parser.parse_args()

    target_path = ROOT / args.target_path
    con = duckdb.connect(str(ROOT / args.db), read_only=True)
    message = build_message(load_results(target_path), con, freshness(target_path), args.title)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(message + "\n", encoding="utf-8")
    print(message)


if __name__ == "__main__":
    main()
