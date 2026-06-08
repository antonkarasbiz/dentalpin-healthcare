<script setup lang="ts">
export interface SlotResult {
  start: string
  end?: string | null
}

defineProps<{ slots: SlotResult[] }>()
const { t } = useI18n()
const { time } = useCopilotFormat()
</script>

<template>
  <div class="rounded-lg border border-default bg-elevated p-3">
    <p class="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted">
      <UIcon name="i-lucide-clock" />
      {{ t('copilot.card.freeSlots') }}
    </p>
    <div class="flex flex-wrap gap-1.5">
      <UBadge
        v-for="(s, i) in slots"
        :key="i"
        color="neutral"
        variant="subtle"
        size="sm"
      >
        {{ time(s.start) }}
      </UBadge>
    </div>
  </div>
</template>
