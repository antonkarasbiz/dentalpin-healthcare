<script setup lang="ts">
// Copilot settings: morning digest opt-in (+ redaction visibility).
// Mounted at /settings/integrations/copilot via the settings registry.
import type { ApiResponse } from '~~/app/types'

interface CopilotSettings {
  provider: string
  model: string
  redaction_enabled: boolean
  digest_enabled: boolean
  digest_hour: number
  digest_recipient_user_id: string | null
}

const { t } = useI18n()
const toast = useToast()
const api = useApi()

const settings = ref<CopilotSettings | null>(null)
const isLoading = ref(false)
const isSaving = ref(false)

const hourOptions = Array.from({ length: 24 }, (_, h) => ({
  label: `${String(h).padStart(2, '0')}:00`,
  value: h
}))

async function load() {
  isLoading.value = true
  try {
    const res = await api.get<ApiResponse<CopilotSettings>>('/api/v1/copilot/settings')
    settings.value = res.data
  } finally {
    isLoading.value = false
  }
}

onMounted(load)

async function save() {
  if (!settings.value || isSaving.value) return
  isSaving.value = true
  try {
    const res = await api.patch<ApiResponse<CopilotSettings>>('/api/v1/copilot/settings', {
      digest_enabled: settings.value.digest_enabled,
      digest_hour: settings.value.digest_hour
    })
    settings.value = res.data
    toast.add({ title: t('copilot.settings.saved'), color: 'success' })
  } catch {
    toast.add({ title: t('common.error'), color: 'error' })
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <USkeleton
      v-if="isLoading && !settings"
      class="h-40 w-full"
    />

    <template v-if="settings">
      <UCard>
        <template #header>
          <div>
            <p class="font-medium">
              {{ t('copilot.settings.digest.title') }}
            </p>
            <p class="text-sm text-muted">
              {{ t('copilot.settings.digest.description') }}
            </p>
          </div>
        </template>

        <div class="flex flex-col gap-4">
          <UFormField :label="t('copilot.settings.digest.enabled')">
            <USwitch v-model="settings.digest_enabled" />
          </UFormField>

          <UFormField
            v-if="settings.digest_enabled"
            :label="t('copilot.settings.digest.hour')"
            :help="t('copilot.settings.digest.hourHelp')"
          >
            <USelect
              v-model="settings.digest_hour"
              :items="hourOptions"
              class="w-full sm:w-40"
            />
          </UFormField>

          <div>
            <UButton
              :loading="isSaving"
              @click="save"
            >
              {{ t('common.save') }}
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard>
        <template #header>
          <p class="font-medium">
            {{ t('copilot.settings.engine.title') }}
          </p>
        </template>
        <div class="flex flex-col gap-2 text-sm">
          <div class="flex justify-between">
            <span class="text-muted">{{ t('copilot.settings.engine.provider') }}</span>
            <span>{{ settings.provider }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted">{{ t('copilot.settings.engine.model') }}</span>
            <span>{{ settings.model }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted">{{ t('copilot.settings.engine.redaction') }}</span>
            <UBadge
              :color="settings.redaction_enabled ? 'success' : 'warning'"
              variant="soft"
            >
              {{ settings.redaction_enabled ? t('copilot.settings.engine.redactionOn') : t('copilot.settings.engine.redactionOff') }}
            </UBadge>
          </div>
        </div>
      </UCard>
    </template>
  </div>
</template>
