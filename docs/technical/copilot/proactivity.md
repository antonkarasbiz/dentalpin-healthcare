# Copilot proactivity — morning digest (v1)

Decision record: [ADR 0014](../../adr/0014-copilot-proactivity.md).
Architecture context: [copilot-agentic-architecture.md](../copilot-agentic-architecture.md).

## What ships in v1

An opt-in daily email per clinic ("Briefing del día") with three
sections, each omitted when empty or when the recipient lacks the
permission:

| Section | Tool called | Permission |
|---|---|---|
| Today's appointments | `agenda.get_day_overview` | `agenda.appointments.read` |
| Overdue recalls | `recalls.list_due_recalls(overdue=true)` | `recalls.read` |
| Budgets awaiting response | `budget.list_budgets(status=['sent'])` | `budget.read` |

No LLM involved: the digest is rendered from a fixed Jinja template
(`templates/email/{es,en}/copilot_morning_digest.html`), subject and
locale resolved from `clinics.settings.communication_language`.

## Moving parts

| Piece | Where |
|---|---|
| Settings columns | `copilot_settings.digest_enabled / digest_hour / digest_recipient_user_id` (migration `cop_0002`) |
| Task | `backend/app/modules/copilot/tasks.py` → `send_morning_digests()` |
| Scheduling | `app/core/scheduler.py`, job `copilot_morning_digests`, hourly at minute 0; the task matches `digest_hour` against the server-local hour |
| Config UI | `/settings/integrations/copilot` (`CopilotSettingsPanel.vue`, registered via `useSettingsRegistry`) |
| Event | `copilot.digest.sent` `{clinic_id, recipient_user_id, date, email_status}` |

## Invariants

- **Data only via `tool_registry.call()`** with an `AgentContext` whose
  permissions are `get_role_permissions(recipient role)`. Never query
  other modules' tables from the task. This is what keeps RBAC parity
  and `depends = []` true for free.
- **Off-books**: the digest contains agenda + recalls + budgets-sent.
  Do not add paid/invoiced sections or any "outstanding" figure.
- **Idempotency**: the hourly gate means at most one send per clinic
  per day per hour value; re-running the task re-sends (acceptable —
  the email is informational).

## Open items

- Clinic-timezone-aware `digest_hour` (currently server-local; same
  caveat as budget reminder crons). Revisit with ADR 0012 multi-tenancy.
- Multi-recipient / per-role digests (v2).
- Event-driven nudges — designed in ADR 0014 §Deferred, not built.
