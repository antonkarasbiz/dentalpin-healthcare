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

# Dashboard de informes

Página de entrada al área de informes. Muestra una tarjeta por
familia: facturación, presupuestos y agenda. Si tienes módulos
adicionales con informes propios (p. ej. `payments`), aparecen como
tarjetas extra contribuidas por el slot `reports.categories`.

## De un vistazo

- **Tres tarjetas nativas** — Facturación, Presupuestos y Agenda.
  Cada una abre su propio dashboard con sus filtros y endpoints
  específicos. Solo ves las tarjetas para las que tienes permiso.
- **Tarjetas aportadas por otros módulos.** El slot
  `reports.categories` permite que un módulo añada su informe. El
  módulo de cobros añade *Informe de cobros* (visible con
  `payments.reports.read`).
- **Datos *on-demand*.** Reports no almacena agregados: cada vista
  llama a sus endpoints y calcula al vuelo. Los rangos largos pueden
  tardar más.
- **Multi-tenancy.** Todo se filtra por clínica activa
  automáticamente.

## Navegación

1. Identifica la familia de informe que necesitas.
2. Pulsa la tarjeta para abrir su dashboard.
3. Cada dashboard tiene sus propios filtros (rango, profesional,
   estado…) y links de *drill-down* hacia el listado base.

## Permisos

| Lo que ves / puedes hacer | Permiso |
|---------------------------|---------|
| Ver el dashboard | al menos uno de los permisos siguientes |
| Tarjeta de facturación | `reports.billing.read` |
| Tarjeta de presupuestos | `reports.budgets.read` |
| Tarjeta de agenda | `reports.scheduling.read` |
| Tarjeta de cobros (la aporta `payments`) | `payments.reports.read` |

## Resolución de problemas

- **No veo ninguna tarjeta.** Tu rol no tiene ninguno de los
  permisos `reports.*` ni `payments.reports.read`. Pide a un admin
  que te conceda al menos uno desde *Ajustes → Usuarios → Roles*.
- **No veo la tarjeta de cobros.** El módulo `payments` no está
  instalado o tu rol no tiene `payments.reports.read`.
- **Una tarjeta abre vacía.** No hay datos para el rango por
  defecto (últimos 90 días). Ajusta el filtro o comprueba que las
  tablas origen contienen datos.
