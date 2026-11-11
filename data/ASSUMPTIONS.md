# Assumptions behind the SIMULATED data

`src/simulate.py`, fixed seed 42, period **2025-01-01 → 2026-09-30** (21 months), refunds and chargebacks
observed until early November 2026. The volumes are deliberately scaled down: they show methods, not the
company's real size or performance.

## Built on the real catalogue (PUBLIC DATA)
- Products, bundle sizes, one-time and subscribe & save prices, and store SKU codes come from the public
  catalogue snapshot (`data/public/catalog_offers.csv`). The three real SKU code styles are kept
  (`ADD_LHFU=3`, `ADD=LHFU3AD`, `ADD=CFOF&QUANTITY=3`).
- VitalPeak shows no price online: an **assumed** ladder is used (39 / 35 / 32 USD one-time, 10% less on
  subscribe & save) with invented store codes (`VP…`).
- Product popularity follows the real number of on-site reviews (damped, `(reviews + 5)^0.75`); kits sell 70% less.

## Activity
| Topic | Assumption |
|---|---|
| Brand mix | PHR 46%, NHMD 15%, PUR 10%, NBL 9%, VPK 7%, TRU 7%, PET 6% |
| Growth and seasonality | +25% a year; January +15%, November +18%, July −15% |
| Ad spend | ~4,500 USD/day at the start, 68% Meta / 32% Google; one EU/UK Meta account in EUR |
| True CPA | 55-80 USD per brand, ±20% per campaign |
| Organic, e-mail, direct | ~13 orders/day across the group (scaled with seasonality) |
| Purchase type | 33% subscribe & save when available; bundle size 1: 45%, 3: 35%, 6: 20% |
| Cross-sell | 15% of orders add a second product of the same brand |
| Repeat buyers | 8% of paid orders and most e-mail orders come from existing customers; 12% of repeats from another brand |
| Countries | US 86%, CA 4%, GB 4% (GBP), IE/DE/FR 6% (EUR) |
| Discounts and shipping | 12% of web orders use a 10% code; 9.95 shipping below 3 units, free on renewals |
| Subscriptions | Interval = 30 days × bundle size. Cancellation before each renewal 24% on the first cycle, −4 pts per cycle, floor 8%. Pause 6% per cycle (30-75 days). Charge success 91%, retries after 3 and 4 days (50%, 40%), then involuntary cancellation. 5% of cancelled come back after 20-90 days. |
| Refunds and chargebacks | 5.5% of orders refunded (80% full), delay ~ exponential with a 35-day mean, capped at 360 days (365-day guarantee); 0.4% chargebacks 25-95 days later, 15 USD fee |
| Payment fees | 2.9% + 0.30; 18% PayPal, 82% Stripe |
| Platform-reported conversions | Meta reports 1.25-1.65× the real orders, Google 1.05-1.3× (view-through, longer windows) |
| FX | Approximate monthly averages, rounded (EUR 1.04-1.17, GBP 1.24-1.36 USD) |
| Finance month close | Net revenue known 5 days after month end, with the payment import errors corrected |

## Issues injected on purpose (answer key: `data/simulated/seed_injected_issues.csv`)
1. A new VitalPeak Meta account opened 2026-05-04; the connector only syncs it from 2026-05-09 (backfilled later) and it is not in the account mapping.
2. A new PHR product (the latest one found in the archive) launched 2026-07-01 without any mapping row.
3. Campaign names: one typo (`PHR_BloodSugr_US_v4`), one wrong brand prefix (a `PHR_` campaign on the Pureance account), one name that matches the wrong product (`PHR_Sleep_StressRelief_Bundle_US`).
4. Time zones: store New York, Google Ads Los Angeles, EU Meta account Vilnius, payments UTC.
5. 0.4% of orders delivered twice by the webhook; the Meta connector loaded 2026-05-14 twice.
6. A dispute wave: 140 extra chargebacks on Feb-Mar 2026 orders, filed in May, after the books were closed.
7. Platform conversions above real orders (see above).
8. EUR and GBP orders next to USD; cents vs units; 25 PayPal charges imported in units instead of cents.
9. The subscription tool shows ACTIVE for paused and past-due subscriptions.
