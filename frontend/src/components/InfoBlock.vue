<script setup>
import { ref } from 'vue';
const props = defineProps(['header'])

const showDetails = ref(false);

</script>

<template>
    <div>
        <div @click="showDetails = !showDetails"
            class="text-center select-none text-gray-500 cursor-pointer hover:text-black mr-1">
            <span>{{ showDetails ? '▼' : '►' }}</span>
            <span>{{ header }}</span>
        </div>
        <div v-show="showDetails" class="border border-gray-600 bg-gray-100 p-1">
            <slot></slot>
        </div>
    </div>
</template>