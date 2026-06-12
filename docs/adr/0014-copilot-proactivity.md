# 0014 — Copilot proactivity v1: deterministic morning digest email

- **Status:** accepted
- **Date:** 2026-06-11
- **Deciders:** Ramón Martínez + AI pair
- **Tags:** copilot, agents, scheduler, email

## Context

The copilot v1 (issue #81, ADR scope in
`docs/technical/copilot-agentic-architecture.md`) deliberately deferred
proactive behaviour. With the tool surface now covering agenda,
recalls, budgets, billing (read) and payments, the highest-value
proactive feature is a small daily push: today's agenda, overdue
recalls and budgets awaiting response — the same data as the "daily
briefing" playbook, delivered without anyone asking.

Candidate delivery channels considered: a seeded copilot conversation
(costs LLM tokens daily whether or not it is read; no push), a
dashboard card (new UI + API + polling), and email (push, zero LLM
cost, reuses core `EmailService` + per-clinic SMTP).

## Decision

Proactivity v1 is an **opt-in, deterministic (no-LLM) morning digest
email**, one recipient per clinic, built by calling READ tools through
the **tool registry** with the recipient's real role permissions.

Clarifications:

- **RBAC for non-interactive contexts**: the digest task builds an
  `AgentContext` whose `permissions = get_role_permissions(role)` for
  the recipient's membership role, and calls `tool_registry.call()` —
  the same chokepoint as the chat bridge. Tools the recipient cannot
  call are silently omitted. No bespoke data queries.
- **No redaction needed**: the digest is human-space output (same trust
  boundary as any notification email to staff); the redactor only
  guards the cloud-LLM path, which the digest never touches.
- **Scheduling**: one hourly APScheduler job (`CronTrigger(minute=0)`)
  filters clinics where `digest_hour == ` server-local hour. Per-clinic
  timezone handling is an explicit open item; budget reminders share
  the same caveat today.
- **Config**: three columns on `copilot_settings`
  (`digest_enabled`, `digest_hour`, `digest_recipient_user_id`).
  Enabling without a recipient defaults to the user flipping the
  switch. Multi-recipient is v2.
- **Off-books safe by construction**: agenda + recalls + budgets-sent
  only. No invoice/payment juxtaposition, no "outstanding debt".
- **Observability**: each send publishes `copilot.digest.sent`.

## Consequences

### Good

- Zero daily LLM cost; failure mode is a missing email, not a wrong one.
- RBAC parity is mechanical (registry chokepoint), not re-implemented.
- Copilot's `depends = []` holds — email via core, data via registry,
  locale via direct `clinics.settings` read.

### Bad / accepted debt

- `app/core/scheduler.py` imports module task functions (copilot,
  budget, notifications, treatment_plan) even when a module is
  uninstalled. The copilot job no-ops without `digest_enabled` rows,
  but the import coupling is real. A registry-driven job registration
  (modules declare jobs in their manifest) is the structural fix —
  tracked as tech debt, applies to all four modules.
- Server-local `digest_hour` is wrong for clinics in other timezones.
  Acceptable for the current deployment; revisit with multi-tenancy
  (ADR 0012).

## Deferred (designed, not built)

Event-driven nudges: copilot subscribes to `appointment.cancelled`,
persists a short-lived `copilot_nudges` row, and the drawer renders a
contextual chip ("Se canceló la cita de las 10:00, ¿busco candidatos de
recall?") feeding the fill-gap playbook. Needs dedupe, same-day expiry
and per-user permission gating. Build only after the digest proves the
proactive channel is read.
