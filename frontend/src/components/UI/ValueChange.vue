<script setup>
const props = defineProps(['value'])

const icon = (value) => {
    return value > 0 ? '▲' + value : value < 0 ? '▼' + Math.abs(value) : '-';
}
// ⬆⬇
</script>

<template>
    <span :class="value > 0 ? 'text-green-500' : value < 0 ? 'text-red-500' : 'text-gray-500'">
        {{ icon(props.value) }}</span>
</template>