"""Measure how many of the injected issues the dbt tests actually caught.

The answer key (data/simulated/seed_injected_issues.csv) lists every problem simulate.py injected,
with a detect_key: the id that should appear in a failing test's rows (an account id, a SKU, a
campaign id, an order id, a month...). The dbt tests never read this file.

For each issue we search the rows that each failing / warning test stored in the `audit` schema
of the BEFORE-FIX warehouse (fix_version = 0). An issue counts as detected only if its key is
found in the stored rows of at least one test. Issues without a key are structural differences
(time zones, attribution windows, currencies): they are explained in the reconciliation bridge,
not alerted, and are reported as such.

Output: data/simulated/detection_results.csv and a printed summary.
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dbt" / "target_before_fix"
DB = ROOT / "dbt" / "impact_brands_before_fix.duckdb"

ISSUE_TYPES = {
    1: "New ad account missing from connector",
    2: "New product without mapping",
    3: "Campaign name: typo or wrong brand",
    4: "Time zone offsets",
    5: "Duplicates (webhook replay, connector re-sync)",
    6: "Late refunds / chargebacks on closed month",
    7: "Platform conversions above real orders",
    8: "Currencies and cents vs units",
    9: "Paused / failing subscriptions counted active",
}


def main():
    issues = pd.read_csv(ROOT / "data" / "simulated" / "seed_injected_issues.csv", dtype={"detect_key": str})
    results = json.loads((TARGET / "run_results.json").read_text(encoding="utf-8"))["results"]
    con = duckdb.connect(str(DB), read_only=True)

    # every value of every stored failing row, per test
    found_values = {}
    for result in results:
        if result["status"] not in ("fail", "warn", "error") or not result.get("relation_name"):
            continue
        test = result["unique_id"].split(".")[2]
        frame = con.sql(f"select * from {result['relation_name']}").df()
        # only text columns (ids, codes, months): a date that happens to equal a key is not a detection
        text = frame.select_dtypes(include=["object", "string"]).astype(str)
        found_values[test] = set(text.to_numpy().ravel())

    rows = []
    for issue in issues.itertuples():
        if pd.isna(issue.detect_key):
            outcome, tests = "structural - explained in reconciliation bridge", ""
        else:
            hits = [t for t, values in found_values.items() if issue.detect_key in values]
            outcome = "detected" if hits else "missed"
            tests = ", ".join(sorted(hits))
        rows.append({"issue_id": issue.issue_id, "issue_type": issue.issue_type,
                     "issue_family": ISSUE_TYPES[issue.issue_type], "description": issue.description,
                     "outcome": outcome, "caught_by": tests})
    report = pd.DataFrame(rows)
    report.to_csv(ROOT / "data" / "simulated" / "detection_results.csv", index=False)

    detectable = report[report.outcome != "structural - explained in reconciliation bridge"]
    caught = (detectable.outcome == "detected").sum()
    pd.set_option("display.width", 200, "display.max_colwidth", 70)
    print(report[["issue_id", "issue_family", "outcome", "caught_by"]].to_string(index=False))
    print(f"\nDetected {caught} of {len(detectable)} injected defects "
          f"({caught / len(detectable):.0%}); {len(report) - len(detectable)} structural differences explained, not alerted.")


if __name__ == "__main__":
    main()
