<script setup lang="ts">
import type { CopilotUiMessage } from '../composables/useCopilot'

const props = defineProps<{ message: CopilotUiMessage }>()
const emit = defineEmits<{ confirm: [callId: string, decision: 'confirm' | 'reject'] }>()
const { t } = useI18n()

const expanded = ref(true)

const toolLabel = computed(() => {
  if (props.message.kind !== 'tool') return ''
  const key =
    props.message.status === 'running'
      ? 'copilot.tool.running'
      : props.message.status === 'failed'
        ? 'copilot.tool.failed'
        : 'copilot.tool.done'
  return t(key, { name: props.message.name })
})

// A finished tool with an object result gets an expandable rich card.
const hasCard = computed(
  () =>
    props.message.kind === 'tool' &&
    props.message.status === 'done' &&
    !!props.message.result &&
    typeof props.message.result === 'object'
)

function toggleCard() {
  if (hasCard.value) expanded.value = !expanded.value
}
</script>

<template>
  <!-- User / assistant text bubble -->
  <div
    v-if="message.kind === 'text'"
    class="flex"
    :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
  >
    <div
      class="max-w-[85%] rounded-lg px-3 py-2 text-sm"
      :class="
        message.role === 'user'
          ? 'whitespace-pre-wrap bg-primary text-inverted'
          : 'bg-elevated text-default'
      "
    >
      <CopilotMarkdown
        v-if="message.role === 'assistant'"
        :text="message.text"
      />
      <template v-else>
        {{ message.text }}
      </template>
    </div>
  </div>

  <!-- Tool-call chip + expandable result card -->
  <div
    v-else-if="message.kind === 'tool'"
    class="px-1 text-xs text-muted"
  >
    <button
      type="button"
      class="flex items-center gap-2"
      :class="hasCard ? 'cursor-pointer hover:text-default' : 'cursor-default'"
      @click="toggleCard"
    >
      <UIcon
        :name="
          message.status === 'running'
            ? 'i-lucide-loader-circle'
            : message.status === 'failed'
              ? 'i-lucide-circle-x'
              : 'i-lucide-circle-check'
        "
        :class="message.status === 'running' ? 'animate-spin' : ''"
      />
      <span>{{ toolLabel }}</span>
      <UIcon
        v-if="hasCard"
        :name="expanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
      />
    </button>
    <div
      v-if="hasCard && expanded"
      class="mt-1.5"
    >
      <CopilotResultCard
        :name="message.name"
        :result="message.result"
      />
    </div>
  </div>

  <!-- Inline confirmation card -->
  <UCard
    v-else-if="message.kind === 'confirmation'"
    :ui="{ body: 'p-3 sm:p-3' }"
  >
    <p class="text-sm font-medium">
      {{ t('copilot.confirm.title') }}
    </p>
    <p class="mt-1 text-sm text-muted">
      {{ t('copilot.confirm.body', { name: message.name }) }}
    </p>
    <pre class="mt-2 overflow-x-auto rounded bg-elevated p-2 text-xs">{{
      JSON.stringify(message.args, null, 2)
    }}</pre>

    <div
      v-if="!message.resolved"
      class="mt-3 flex justify-end gap-2"
    >
      <UButton
        color="neutral"
        variant="ghost"
        size="sm"
        @click="emit('confirm', message.callId, 'reject')"
      >
        {{ t('copilot.confirm.reject') }}
      </UButton>
      <UButton
        color="primary"
        size="sm"
        @click="emit('confirm', message.callId, 'confirm')"
      >
        {{ t('copilot.confirm.approve') }}
      </UButton>
    </div>
    <p
      v-else
      class="mt-2 text-xs text-muted"
    >
      {{ message.resolved === 'confirm' ? t('copilot.confirm.approved') : t('copilot.confirm.rejected') }}
    </p>
  </UCard>
</template>
