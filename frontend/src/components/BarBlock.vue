<script setup>
const props = defineProps(['stat', 'scale'])

// console.log(props.stat)

const scaleX = 100;
const bar1 = Math.round((props.stat.score - Math.max(props.stat.score_change, 0)) / props.scale * scaleX)
const bar2 = Math.round((Math.abs(props.stat.score_change)) / props.scale * scaleX)
// console.log(bar1, bar2)

const itemStyle = props.stat.score_change > 0 ? 'bg-green-200' : 'bg-white border border-black border-dashed'


</script>

<template>
    <div class="lg:flex  text-sm hidden pr-3 mt-1 select-none">
        <!-- justify-center items-center -->
        <div :style="`width: ${bar1}%`" class="h-6 bg-green-400 flex items-center px-1 border">
        </div>
        <div v-show="stat.score_change != 0" :style="`width: ${bar2}%`" class="h-6  flex items-center justify-center"
            :class="itemStyle">
        </div>
    </div>

</template>