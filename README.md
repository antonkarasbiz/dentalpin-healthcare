# DentalPin

Open-source dental clinic platform for patients, odontogram, scheduling, treatment plans, billing, and a built-in AI copilot. Modular, self-hosted, and API-first.

## Overview

DentalPin is a healthcare operations system: one clinic workspace for records, appointments, budgets, and payments, with an agent that can execute the same actions a staff member is allowed to perform. It is part of the full-stack and applied-AI portfolio under [antonkarasbiz](https://github.com/antonkarasbiz).

Demo: [demo.dentalpin.com](https://demo.dentalpin.com)

## Capabilities

- Patient records and odontogram
- Appointment scheduling and recalls
- Treatment plans, budgets, and payments
- Practice dashboard and reporting
- Role-based access control
- Agentic AI copilot with tool calling
- PHI redaction before cloud LLM calls
- Confirmation gates on write actions
- Morning briefing playbooks that can run without an LLM

## AI copilot

The copilot is not a chat overlay. It plans multi-step work — find a patient, free a slot, chase an unanswered budget — and calls the same module APIs as the UI. Every tool execution is re-checked against the caller’s RBAC scope. Writes pause for explicit confirmation.

Architecture notes: [docs/technical/copilot-agentic-architecture.md](docs/technical/copilot-agentic-architecture.md)

## Tech stack

- Python backend (`backend/`)
- React / TypeScript frontend (`frontend/`)
- PostgreSQL for clinic data
- Modular tool registry for the copilot
- Vendor-agnostic LLM provider abstraction

## Getting started

```bash
# Backend
cd backend
# follow backend/pyproject.toml for the local Python environment

# Frontend
cd frontend
npm install
npm run dev
```

Use environment files for database, auth, and model-provider settings. Never commit clinic data or API keys.

Additional languages: [Español](README.es.md) · [Français](README.fr.md) · [தமிழ்](README.ta.md)

## Screenshots

See the original screenshot set in `docs/screenshots/` for dashboard, patients, schedule, and copilot views.

## Maintainer

[Anton Karas](https://github.com/antonkarasbiz) — full-stack, blockchain, and AI engineering.
