<script setup lang="ts">
const props = defineProps<{
  error: {
    statusCode?: number
    statusMessage?: string
    message?: string
  }
}>()

const statusCode = computed(() => props.error?.statusCode || 500)
const statusMessage = computed(
  () =>
    props.error?.statusMessage ||
    props.error?.message ||
    (statusCode.value === 404 ? 'Страница не найдена' : 'Ошибка')
)
</script>

<template>
  <NotFoundShell
    :status-code="statusCode"
    :status-message="statusMessage"
  />
</template>
