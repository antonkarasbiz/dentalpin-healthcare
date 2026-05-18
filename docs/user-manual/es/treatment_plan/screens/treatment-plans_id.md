---
module: treatment_plan
screen: detail
route: /treatment-plans/[id]
related_endpoints:
  - DELETE /api/v1/treatment_plan/treatment-plans/{plan_id}
  - DELETE /api/v1/treatment_plan/treatment-plans/{plan_id}/items/{item_id}
  - GET /api/v1/treatment_plan/treatment-plans
  - GET /api/v1/treatment_plan/treatment-plans/patient/{patient_id}
  - GET /api/v1/treatment_plan/treatment-plans/pipeline
  - GET /api/v1/treatment_plan/treatment-plans/{plan_id}
  - PATCH /api/v1/treatment_plan/treatment-plans/{plan_id}/items/reorder
  - PATCH /api/v1/treatment_plan/treatment-plans/{plan_id}/items/{item_id}/complete
  - PATCH /api/v1/treatment_plan/treatment-plans/{plan_id}/status
  - POST /api/v1/treatment_plan/treatment-plans
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/close
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/confirm
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/contact-log
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/generate-budget
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/items
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/link-budget
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/reactivate
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/reopen
  - POST /api/v1/treatment_plan/treatment-plans/{plan_id}/sync-budget
  - PUT /api/v1/treatment_plan/treatment-plans/{plan_id}
  - PUT /api/v1/treatment_plan/treatment-plans/{plan_id}/items/{item_id}
related_permissions:
  - treatment_plan.plans.read
  - treatment_plan.plans.write
  - treatment_plan.plans.confirm
  - treatment_plan.plans.close
  - treatment_plan.plans.reactivate
related_paths:
  - backend/app/modules/treatment_plan/frontend/pages/treatment-plans/[id].vue
  - backend/app/modules/treatment_plan/router.py
last_verified_commit: b1b82f5
---

# Detalle del plan de tratamiento

Vista del plan: cabecera con paciente, profesional y estado;
columna principal con los ítems (catálogo o tratamiento odontograma)
y columna lateral con presupuesto enlazado, ejecuciones y contactos.
Aquí se confirma, sincroniza con el presupuesto, marca ítems como
ejecutados y se cierra o reactiva.

## De un vistazo

- **Estado y chip.** El chip en la cabecera refleja el estado:
  `draft`, `pending`, `active`, `completed`, `closed`. Las acciones
  cambian según el estado.
- **Ítems** — añadir, reordenar, completar. Cada ítem referencia un
  ítem del catálogo y, opcionalmente, un tratamiento del odontograma.
  Al completar un ítem se publica
  `treatment_plan.treatment_completed` (con `treatment_category_key`
  para recalls).
- **Presupuesto enlazado.** Botones **Generar presupuesto** /
  **Enlazar con presupuesto existente** / **Sincronizar** según el
  caso. El plan publica `treatment_plan.treatment_added /
  _removed / budget_sync_requested` para que `budget` mantenga el
  presupuesto al día.
- **Contactos** — historial de toques de recepción. Útil cuando el
  plan está en *pendiente* esperando aceptación.
- **Notas clínicas.** Pueden engancharse al plan desde el módulo
  `clinical_notes` (slot `patient.detail.clinical.notes`).

## Confirmar un plan

> Requiere `treatment_plan.plans.confirm`.

1. Sobre un plan en `draft`, pulsa **Confirmar**.
2. Se publica `treatment_plan.confirmed`. El plan pasa a `pending`.
3. Si no había presupuesto enlazado, **Generar presupuesto** crea
   uno nuevo en el módulo `budget`.

## Marcar ítems como ejecutados

> Requiere `treatment_plan.plans.write`.

1. En el ítem, pulsa **Marcar como hecho**.
2. Se publica `treatment_plan.treatment_completed`. `recalls` puede
   sugerir un próximo recall basado en `treatment_category_key`.
3. Para anotar una nota clínica en ese momento, usa el botón de
   *Añadir nota* (lo aporta `clinical_notes`).

## Cerrar o reactivar

> Cerrar requiere `treatment_plan.plans.close`. Reactivar requiere
> `treatment_plan.plans.reactivate`.

1. **Cerrar** — elige motivo: rechazado, expirado, cancelado,
   abandono u *otro*. Publica `treatment_plan.closed` con
   `closure_reason`.
2. **Reactivar** — vuelve al estado `draft`. Publica
   `treatment_plan.reactivated`.

## Permisos

| Lo que ves / puedes hacer | Permiso |
|---------------------------|---------|
| Ver detalle, ítems y contactos | `treatment_plan.plans.read` |
| Añadir/reordenar ítems, completarlos, registrar contactos | `treatment_plan.plans.write` |
| Confirmar (draft → pending) | `treatment_plan.plans.confirm` |
| Cerrar | `treatment_plan.plans.close` |
| Reactivar | `treatment_plan.plans.reactivate` |

## Resolución de problemas

- **Confirmé el plan pero el presupuesto no aparece.** Pulsa
  **Generar presupuesto** o **Enlazar con presupuesto existente**.
  Confirmar no crea automáticamente el presupuesto a menos que se
  use *Generar* después.
- **El paciente aceptó el presupuesto pero el plan sigue en
  pendiente.** Comprueba que el evento `budget.accepted` está
  fluyendo (el módulo `budget` ha de estar instalado y el
  presupuesto realmente aceptado). El handler
  `on_budget_accepted` lo mueve a *activo*.
- **No puedo borrar un ítem.** El ítem ya está marcado como hecho.
  Los ítems completados quedan como histórico.
- **No me deja completar un ítem.** Tu rol no tiene
  `treatment_plan.plans.write`.
