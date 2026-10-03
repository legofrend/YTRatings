<script setup>
import { computed } from 'vue';
const props = defineProps(['stat', 'scale'])


const scaleX = 100;
// const bar1 = Math.round((props.stat.score - Math.max(props.stat.score_change, 0)) / props.scale * scaleX)
// const bar2 = Math.round((Math.abs(props.stat.score_change)) / props.scale * scaleX)

const bar1 = computed(() => {
    return Math.round((props.stat.score - Math.max(props.stat.score_change, 0)) / props.scale * scaleX)
})

const bar2 = computed(() => {
    return Math.round((Math.abs(props.stat.score_change)) / props.scale * scaleX)
})


// console.log('Stat', props.stat)
// console.log('Bars', bar1.value, bar2.value)

const itemStyle = props.stat.score_change > 0 ? 'bg-green-100' : 'bg-white border border-black border-dashed'


</script>

<template>
    <div class="lg:flex  text-sm hidden pr-3 mt-1 select-none">
        <!-- justify-center items-center -->
        <div :style="`width: ${bar1}%`" class="h-6 bg-blue-200 flex items-center px-1 border">
        </div>
        <div v-show="stat.score_change != 0" :style="`width: ${bar2}%`" class="h-6  flex items-center justify-center"
            :class="itemStyle">
        </div>
    </div>

</template>