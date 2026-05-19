---
module: patients
screen: detail
route: /patients/[id]
related_endpoints:
  - GET /api/v1/patients/{patient_id}
  - PUT /api/v1/patients/{patient_id}
  - DELETE /api/v1/patients/{patient_id}
  - GET /api/v1/patients/{patient_id}/extended
  - PUT /api/v1/patients/{patient_id}/extended
related_permissions:
  - patients.read
  - patients.write
related_paths:
  - backend/app/modules/patients/router.py
  - backend/app/modules/patients/frontend/pages/patients/[id].vue
last_verified_commit: 0e9a0ac
---

# Patient detail

The single-patient view. Combines identity, extended demographics,
clinical-tab content provided by sibling modules, and an actions slot
that other modules contribute to.

## Layout

- **Summary hero** — name, photo, birthday, contact, key flags
  (`do_not_contact`, archived, etc.).
- **Actions slot** — buttons contributed by sibling modules:
  - **Recalls** → *Set recall*
  - **Notifications** → *Send message*
  - More appear automatically as new modules register slot content.
- **Tabs** — clinical-tab content (notes, treatments, photos, plans,
  budgets, etc.) supplied by other modules. Each tab respects its own
  permission gates.

## Editing identity

> Requires `patients.write`.

1. Click the pencil icon in the summary hero, or the **Edit** button on
   the *Identity* sub-tab.
2. Update name, contact, ID document, demographics. Extended demographics
   live behind the *Identity → Extended* tab and are persisted via the
   `/extended` endpoint.
3. **Save** publishes a `patient.updated` event with the changed fields,
   so dependents (recalls, notifications, …) can react.

## Archiving a patient

> Requires `patients.write`. Patients are **never** hard-deleted.

1. Open the **⋮ More** menu in the summary hero.
2. Click **Archive patient**.
3. Confirm. The patient's `status` flips to `archived`, the row is
   hidden from default lists, and a `patient.archived` event is
   published.
4. To restore, run an SQL update on the `status` column — there is no
   in-app un-archive flow yet.

## Payments tab — "Pending to charge"

The **Administration → Payments** tab shows the patient ledger
(total paid, debt, on-account balance) and, when there is real debt,
a **Pending to charge** card at the top.

- The card lists the recently completed sessions that net payments
  haven't covered yet (FIFO).
- Total equals `clinic_receivable = earned − net_paid`.
- The **Collect X €** button opens the payment modal with the amount
  pre-filled; reception just picks the method and confirms.
- After the payment is recorded, the card disappears (or shrinks)
  depending on how much was collected.

## "Do not contact"

The `do_not_contact` flag is the operational opt-out. When enabled:

- Recalls module excludes the patient from any recall queue.
- Future outreach modules (email, SMS) MUST honour the flag.
- The patient still appears in the list and can be opened normally —
  they just won't be pestered automatically.

## Permissions

| You see / can do | Permission |
|------------------|-----------|
| View the detail | `patients.read` |
| Edit identity / extended | `patients.write` |
| Archive | `patients.write` |
| Sibling-module actions (recalls, notifications, …) | The sibling module's permissions. |

## Troubleshooting

- **Edit and Archive buttons are hidden.** Your role lacks
  `patients.write`. An admin can grant it via *Settings → Users → Roles*.
- **A tab I expected isn't there.** That tab is contributed by a
  sibling module (e.g. *Treatment plans*). Make sure that module is
  installed and you have its read permission.
