# Coupon/Deal Source Research (Digital vs Physical)

Date: 2026-03-03  
Scope: validate currently active online coupon/sale sources to expand Deal Finder coverage and classify offers by item type.

## Verified Live Sources

| Source | URL | Evidence of Active Coupons/Deals | Category Bias |
|---|---|---|---|
| Slickdeals | https://slickdeals.net/ | Live front-page deals and dedicated coupons navigation | Physical-heavy |
| DealNews Coupons | https://www.dealnews.com/coupons/ | Live coupon feed with expiration dates and merchant pages | Physical-heavy |
| CouponFollow | https://couponfollow.com/ | Active promo-code listings by merchant | Mixed |
| Groupon Coupons | https://www.groupon.com/coupons | Active merchant coupon pages + daily sale offers | Physical-heavy |
| AppSumo | https://appsumo.com/ | Software/SaaS promotions and lifetime deal campaigns | Digital-heavy |
| StackSocial | https://www.stacksocial.com/ | Marketplace for software licenses and digital bundles | Digital-heavy |

## Implementation Decisions From Research

1. Keep existing structured fetchers (`slickdeals`, `retailmenot`, `couponscom`).
2. Add a new `web_research` source that queries latest coupon/sale pages and captures additional domains above.
3. Add item category tagging (`digital`, `physical`, `unknown`) to both deals and coupons.
4. Expose source diagnostics (`urls_checked`) so the agent can explain exactly where it searched.

## Domain Heuristics Used

- Digital-focused domains: `appsumo.com`, `stacksocial.com` (plus existing digital keyword matching).
- Physical-focused domains: `slickdeals.net`, `dealnews.com`, `groupon.com` (plus retail keyword matching).
- Mixed domains: `couponfollow.com` and generic coupon aggregators.

## Notes

- This is a development-only environment; source catalog is intentionally easy to update in code as sites evolve.
- The new `web_research` path uses date-filtered search queries (`past_month`) to bias toward latest coupons/sales.
