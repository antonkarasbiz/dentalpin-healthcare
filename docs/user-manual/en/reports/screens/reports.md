---
module: reports
screen: list
route: /reports
related_endpoints:
  - GET /api/v1/reports/billing/by-payment-method
  - GET /api/v1/reports/billing/by-professional
  - GET /api/v1/reports/billing/gaps
  - GET /api/v1/reports/billing/overdue
  - GET /api/v1/reports/billing/summary
  - GET /api/v1/reports/billing/vat-summary
  - GET /api/v1/reports/budgets/by-professional
  - GET /api/v1/reports/budgets/by-status
  - GET /api/v1/reports/budgets/by-treatment
  - GET /api/v1/reports/budgets/summary
  - GET /api/v1/reports/scheduling/by-cabinet
  - GET /api/v1/reports/scheduling/by-day-of-week
  - GET /api/v1/reports/scheduling/by-professional
  - GET /api/v1/reports/scheduling/duration-variance
  - GET /api/v1/reports/scheduling/first-visits
  - GET /api/v1/reports/scheduling/funnel
  - GET /api/v1/reports/scheduling/punctuality
  - GET /api/v1/reports/scheduling/summary
  - GET /api/v1/reports/scheduling/waiting-times
related_permissions:
  - reports.billing.read
  - reports.budgets.read
  - reports.scheduling.read
related_paths:
  - backend/app/modules/reports/frontend/pages/reports/index.vue
  - backend/app/modules/reports/router.py
last_verified_commit: b1b82f5
---

# Reports dashboard

Entry page for the reports area. Shows one card per family:
billing, budgets, and agenda. If you have extra modules with their
own reports (e.g. `payments`), they appear as additional cards
contributed by the `reports.categories` slot.

## At a glance

- **Three native cards** — Billing, Budgets, and Agenda. Each opens
  its own dashboard with its specific filters and endpoints. You
  only see the cards you have permission for.
- **Cards from other modules.** The `reports.categories` slot lets
  any module add its report. The payments module adds *Payment
  reports* (visible with `payments.reports.read`).
- **On-demand data.** Reports doesn't store aggregates: each view
  hits its endpoints and computes on the fly. Long ranges may take
  longer.
- **Multi-tenancy.** Everything filters by active clinic
  automatically.

## Navigation

1. Identify the report family you need.
2. Click the card to open its dashboard.
3. Each dashboard has its own filters (range, professional,
   status…) and drill-down links to the base list.

## Permissions

| What you see / can do | Permission |
|-----------------------|------------|
| View the dashboard | at least one of the permissions below |
| Billing card | `reports.billing.read` |
| Budgets card | `reports.budgets.read` |
| Agenda card | `reports.scheduling.read` |
| Payments card (contributed by `payments`) | `payments.reports.read` |

## Troubleshooting

- **No cards show up.** Your role lacks any of the `reports.*` or
  `payments.reports.read` permissions. Ask an admin to grant at
  least one under *Settings → Users → Roles*.
- **No payments card.** The `payments` module is not installed or
  your role lacks `payments.reports.read`.
- **A card opens empty.** No data for the default range (last 90
  days). Adjust the filter or verify the source tables contain
  data.
