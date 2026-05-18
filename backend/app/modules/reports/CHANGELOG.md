# Changelog — reports module

## Unreleased

- fix(i18n): ``useReports.getPaymentMethodLabel`` was calling the non-existent ``invoice.paymentMethods.*`` i18n key and rendering the raw key as fallback; now uses the shared ``paymentMethodLabel`` util reading the canonical ``invoice.payments.methods.*`` path.
- safety(billing-overdue): ``GET /reports/billing/overdue`` accepts a
  ``limit`` query parameter (default 200, max 1000) and the service
  enforces it. Previously the endpoint returned every overdue
  invoice for a clinic, which scaled with years of unpaid balance.
- docs(user-manual): reescribir pantallas con guía operativa (ES + EN).
- Added per-module `CLAUDE.md` for AI-agent context (2026-04-27).

## 0.1.0 — initial

- Billing, budget, and scheduling report families.
- Read-only across the business modules.
