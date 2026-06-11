# Copilot module

Conversational AI agent over DentalPin (issue #81). A thin **surface**
over the core agentic engine (`app/core/agents` + `app/core/llm`): it
persists conversations, streams chat over SSE, and gates writes with
inline confirmation. RBAC parity is the whole point — the agent can
never see or do anything the calling user couldn't through the UI.

## Public API

Routes mounted at `/api/v1/copilot/`.

- `POST   /sessions`                          — create chat session; `copilot.chat`
- `GET    /sessions`                          — list (own, or all with `read_all`); `copilot.history.read`
- `GET    /sessions/{id}/messages`            — replay transcript; `copilot.history.read`
- `POST   /sessions/{id}/messages`            — send a turn, **SSE** stream; `copilot.chat`
- `POST   /sessions/{id}/confirmations/{cid}` — confirm/reject a pending write, **SSE**; `copilot.chat`
- `POST   /sessions/{id}/end`                 — close; `copilot.chat`
- `GET    /settings` · `PATCH /settings`      — provider/model/budget; `copilot.configure`

SSE events: `token`, `tool_call`, `tool_result`, `confirmation_required`,
`usage`, `done`, `budget_exceeded`, `error`.

## Dependencies

`manifest.depends = []`. Copilot consumes tools through the global
registry only; it never imports another module's service. Modules
participate by registering their own `tools.py`.

## Permissions

`copilot.chat`, `copilot.history.read`, `copilot.history.read_all`,
`copilot.supervise`, `copilot.configure` (declared relative; registry
namespaces them).

## Tools exposed

None — copilot is a consumer, not a provider, of tools.

## Events emitted

| Event | When | Payload keys |
|---|---|---|
| `copilot.session.started` | new conversation | `clinic_id`, `conversation_id`, `user_id` |
| `copilot.session.ended` | conversation closed | `clinic_id`, `conversation_id` |
| `copilot.digest.sent` | morning digest emailed | `clinic_id`, `recipient_user_id`, `date`, `email_status` |

(`copilot.tool.invoked` / `copilot.budget.threshold_reached` are reserved
for the dashboards milestone.)

## Lifecycle

- `installable=True`, `auto_install=False` (optional module, opt-in per
  project rule), `removable=True`. Own Alembic branch `("copilot",)`.

## Gotchas / non-obvious invariants

- **Inline confirmation, not the approval queue.** A WRITE/DESTRUCTIVE
  tool suspends the turn (an assistant `tool_use` block with no matching
  `tool_result` in `copilot_messages`); the user resolves it via the
  confirmations endpoint. The core `AgentApprovalQueue` is reserved for
  the later service/supervisor mode. `COPILOT_GUARDRAILS` disables the
  queue triggers but keeps rate limits + denylist.
- **History is real space.** `copilot_messages` store real values; the
  redactor tokenizes only on the way to the provider. Tokens are
  deterministic, so a resumed turn re-derives the same token.
- **`AgentContext.permissions = get_role_permissions(role)`** — identical
  to what routers enforce. Every tool call re-checks at the chokepoint.
- **PHI redaction is mandatory** by default (`copilot_settings.redaction_enabled`).
  Tools flagged `exposes_free_text` are excluded from the cloud path.
- **SSE owns its DB session.** Streaming endpoints open their own
  `async_session_maker` session for the stream, not `Depends(get_db)`.
- **Morning digest (proactivity v1).** `tasks.py::send_morning_digests`
  runs hourly from `app/core/scheduler.py` and emails a deterministic
  (no-LLM) briefing to opted-in clinics
  (`copilot_settings.digest_enabled/digest_hour/digest_recipient_user_id`,
  migration `cop_0002`). Data is gathered ONLY via `tool_registry.call()`
  with the recipient's role permissions — never query other modules'
  tables from the task. Config UI at `/settings/integrations/copilot`.
  Design: `docs/technical/copilot/proactivity.md` + ADR 0014.

## Related ADRs / docs

- `docs/technical/copilot-agentic-architecture.md` (the full plan)
- `docs/adr/0001-modular-plugin-architecture.md`
- `docs/adr/0002-per-module-alembic-branches.md`

## CHANGELOG

See `./CHANGELOG.md`.
