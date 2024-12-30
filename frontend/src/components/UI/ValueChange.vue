<script setup>
const props = defineProps(['value'])


const ValDisplay = (value) => {
    const absValue = Math.abs(value);
    var val = absValue
    if (absValue > 10 ** 6) {
        val = (Math.round(absValue / 10 ** 6 * 10) / 10);
        return val.toFixed(1) + 'M';
    }
    if (absValue > 1000) {
        val = (Math.round(absValue / 10 ** 3));
        return val.toFixed(0) + 'K';
    }
    return val
}


const icon = (value) => {
    const val = ValDisplay(value)
    // console.log('value', value)
    // console.log('ValDisplay', val)
    return value > 0 ? '▲' + val : value < 0 ? '▼' + val : '-';

}
// ⬆⬇
</script>

<template>
    <span v-if="value > 0" class="text-green-500">▲</span>
    <span v-else-if="value < 0" class="text-red-500">▼</span>
    <span v-else class="text-gray-500">-</span>
    <span v-if="value != 0"> {{ ValDisplay(props.value) }}</span>


    <!-- <span :class="value > 0 ? 'text-green-500' : value < 0 ? 'text-red-500' : 'text-gray-500'">
        {{ icon(props.value) }}</span> -->
</template>