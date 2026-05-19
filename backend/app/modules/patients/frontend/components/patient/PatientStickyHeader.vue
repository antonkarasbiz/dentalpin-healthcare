<script setup lang="ts">
/**
 * PatientStickyHeader — persistent patient context bar.
 *
 * Renders at the top of the patient-detail page above the UTabs strip
 * and stays in view as the user scrolls into deep tabs (Clinical →
 * Plans → detail, Administración → Cobros, etc.). Replaces the legacy
 * dense left rail that lived inside the Resumen tab.
 *
 * Cross-module contributions plug in via two slots:
 *
 *   - ``patient.header.alerts``  — clinical chips (allergy, pregnancy,
 *                                  anticoagulant) provided by the
 *                                  ``patients_clinical`` module.
 *   - ``patient.summary.actions`` — module-contributed action buttons
 *                                   (recalls "Set recall", etc.). Kept
 *                                   under the legacy slot name to avoid
 *                                   breaking sibling modules.
 *
 * The host (``patients``) never imports any sibling module — it only
 * exposes the slot names.
 */

import type { PatientExtended } from '~~/app/types'

interface Props {
  patient: PatientExtended
}

const props = defineProps<Props>()

const emit = defineEmits<{
  edit: []
  back: []
  archive: []
  newAppointment: []
  newNote: []
  collect: []
}>()

const { t } = useI18n()

const fullName = computed(() => `${props.patient.first_name} ${props.patient.last_name}`)

const initials = computed(() => {
  const first = props.patient.first_name?.[0] ?? ''
  const last = props.patient.last_name?.[0] ?? ''
  return (first + last).toUpperCase() || '?'
})

const age = computed(() => {
  if (!props.patient.date_of_birth) return null
  const today = new Date()
  const birth = new Date(props.patient.date_of_birth)
  let years = today.getFullYear() - birth.getFullYear()
  const m = today.getMonth() - birth.getMonth()
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) years--
  return years
})

const statusColor = computed(() => props.patient.status === 'active' ? 'success' : 'neutral')

const actionItems = computed(() => [
  {
    label: t('patientDetail.actions.newAppointment', 'Nueva cita'),
    icon: 'i-lucide-calendar-plus',
    onSelect: () => emit('newAppointment')
  },
  {
    label: t('patientDetail.actions.collect', 'Cobrar'),
    icon: 'i-lucide-wallet',
    onSelect: () => emit('collect')
  },
  {
    label: t('patientDetail.actions.newNote', 'Nueva nota'),
    icon: 'i-lucide-edit',
    onSelect: () => emit('newNote')
  },
  {
    type: 'separator' as const
  },
  {
    label: t('patients.archive'),
    icon: 'i-lucide-archive',
    color: 'error' as const,
    onSelect: () => emit('archive')
  }
])
</script>

<template>
  <header
    class="patient-sticky-header sticky top-0 z-30 -mx-4 sm:mx-0 bg-surface/85 backdrop-blur border-b border-default px-4 sm:px-0 sm:pl-1 sm:pr-2 py-2"
    aria-label="Cabecera del paciente"
  >
    <div class="flex items-center gap-3">
      <UButton
        variant="ghost"
        color="neutral"
        size="sm"
        icon="i-lucide-arrow-left"
        :aria-label="t('common.back', 'Volver')"
        @click="emit('back')"
      />

      <UAvatar
        v-if="patient.photo_url"
        :src="patient.photo_url"
        :alt="fullName"
        size="md"
        class="shrink-0"
      />
      <UAvatar
        v-else
        :text="initials"
        size="md"
        class="shrink-0"
      />

      <!-- Identity -->
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline gap-2 flex-wrap min-w-0">
          <h1 class="text-h1 text-default truncate">
            {{ fullName }}
          </h1>
          <UBadge
            :color="statusColor"
            size="xs"
            variant="subtle"
          >
            {{ patient.status === 'active' ? t('patients.status.active') : t('patients.status.archived') }}
          </UBadge>
        </div>

        <div class="flex items-center gap-x-3 gap-y-0.5 flex-wrap text-caption text-muted">
          <span
            v-if="age != null"
            class="inline-flex items-center gap-1 tnum"
          >
            <UIcon
              name="i-lucide-cake"
              class="w-3.5 h-3.5"
            />
            {{ age }} {{ t('patients.years') }}
          </span>
          <span
            v-if="patient.national_id"
            class="inline-flex items-center gap-1 tnum"
          >
            <UIcon
              name="i-lucide-id-card"
              class="w-3.5 h-3.5"
            />
            {{ patient.national_id_type?.toUpperCase() }} {{ patient.national_id }}
          </span>
          <a
            v-if="patient.phone"
            :href="`tel:${patient.phone}`"
            class="inline-flex items-center gap-1 tnum text-primary-accent hover:underline"
          >
            <UIcon
              name="i-lucide-phone"
              class="w-3.5 h-3.5"
            />
            {{ patient.phone }}
          </a>
          <a
            v-if="patient.email"
            :href="`mailto:${patient.email}`"
            class="hidden md:inline-flex items-center gap-1 text-primary-accent hover:underline truncate max-w-[18rem]"
          >
            <UIcon
              name="i-lucide-mail"
              class="w-3.5 h-3.5 shrink-0"
            />
            <span class="truncate">{{ patient.email }}</span>
          </a>
        </div>
      </div>

      <!-- Slot: clinical alerts chips (provided by patients_clinical) -->
      <div class="hidden lg:flex items-center gap-1.5 max-w-md overflow-x-auto">
        <ModuleSlot
          name="patient.header.alerts"
          :ctx="{ patient }"
        />
      </div>

      <!-- Module actions slot (recalls 'Set recall', etc.) -->
      <div class="hidden md:flex items-center gap-1.5">
        <ModuleSlot
          name="patient.summary.actions"
          :ctx="{ patient }"
        />
      </div>

      <!-- Edit + Acciones -->
      <UButton
        variant="outline"
        color="neutral"
        size="sm"
        icon="i-lucide-pencil"
        :aria-label="t('patientDetail.editPatient', 'Editar paciente')"
        class="shrink-0"
        @click="emit('edit')"
      >
        <span class="hidden sm:inline">{{ t('patientDetail.edit', 'Editar') }}</span>
      </UButton>

      <UDropdownMenu :items="actionItems">
        <UButton
          color="primary"
          size="sm"
          trailing-icon="i-lucide-chevron-down"
          icon="i-lucide-plus"
          class="shrink-0"
        >
          <span class="hidden sm:inline">{{ t('patientDetail.actions.label', 'Acciones') }}</span>
        </UButton>
      </UDropdownMenu>
    </div>

    <!-- Mobile-only alerts row (chips wrap below identity when present) -->
    <div class="lg:hidden mt-1.5 empty:hidden flex flex-wrap items-center gap-1.5">
      <ModuleSlot
        name="patient.header.alerts"
        :ctx="{ patient }"
      />
    </div>
  </header>
</template>
