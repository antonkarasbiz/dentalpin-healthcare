---
module: billing
last_verified_commit: 0000000
---

# Billing — events

Per-module slice of [`docs/events-catalog.md`](../../events-catalog.md)
(auto-generated). Update both files when adding or removing events.

## Published

_This module does not publish any events._

## Subscribed

| Event | Handler | Effect |
|-------|---------|--------|
| `payment.refunded` | `events.py:on_payment_refunded` | Recompute status of invoices whose `invoice_payments` link the refunded payment (`paid → partial`, `partial → issued`). |
| `clinic.created` | `events.py:on_clinic_created` | Create the default `FAC` (invoice) and `RECT` (credit note) series when the clinic has none. |

## Adding a new event

1. Add the constant to `backend/app/core/events/types.py` (`EventType`).
2. Publish from a service method, after the DB commit succeeds.
3. Add the row to the table(s) above.
4. Run `python backend/scripts/generate_catalogs.py` to refresh the
   global catalog.
