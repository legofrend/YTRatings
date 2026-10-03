<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Short friendly title */
    message?: string
    /** Call-to-action under the title */
    hint?: string
    /** Tighter padding for nested panels */
    compact?: boolean
  }>(),
  {
    message: 'Не удалось загрузить данные',
    hint: 'Нажмите, чтобы повторить',
    compact: false,
  }
)

defineEmits<{ retry: [] }>()
</script>

<template>
  <button
    type="button"
    class="group w-full text-center rounded-lg border border-dashed border-gray-300 bg-gray-50/80 text-gray-600 transition hover:border-gray-400 hover:bg-gray-100 hover:text-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60"
    :class="compact ? 'px-2 py-2 text-xs' : 'px-4 py-5 text-sm'"
    @click="$emit('retry')"
  >
    <span class="block font-medium">{{ message }}</span>
    <span
      class="mt-0.5 block text-[0.9em] text-gray-500 group-hover:text-blue-600 group-hover:underline"
    >
      {{ hint }}
    </span>
  </button>
</template>
