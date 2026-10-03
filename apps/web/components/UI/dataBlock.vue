<script setup>
import { computed } from 'vue';
import ValueChange from './ValueChange.vue';
const props = defineProps({
  value: null,
  valueChange: null,
  title: String,
  type: String,
  /** Wider cells for category aggregate (big sums). */
  wide: { type: Boolean, default: false },
})

const image = {
    views: '/img/iconView.svg',
    score: '/img/iconIndex.svg',
    subscribers: '/img/iconSubscriber.svg',
    likes: '/img/iconLike.svg',
    clickbaits: '/img/iconClickbaitBlack.svg',
    comments: '/img/iconComment.svg',
    videos: '/img/iconVideoColor.svg',
    shorts: '/img/iconShortColor.svg',
    time: '/img/iconTime.svg',
}

const style = computed(() => {
    const wide = props.wide
    if (props.type === 'time') {
        return wide
          ? 'bg-black text-white w-10 sm:w-12 shrink-0'
          : 'bg-black text-white w-8 shrink-0'
    } else if (props.type == 'views' || props.type == 'subscribers') {
        return wide
          ? 'bg-blue-50 w-12 sm:w-14 shrink-0'
          : 'bg-blue-50 w-10 shrink-0'
    } else {
        return wide
          ? 'bg-blue-50 w-10 sm:w-12 shrink-0'
          : 'bg-blue-50 w-8 shrink-0'
    }
})
</script>

<template>
    <div class="flex flex-col px-2 py-1 items-center rounded-md shadow-md" :class="style" :title="title">
        <img :src="image[type]" class="h-4 mb-1" alt="">
        <div class="tabular-nums whitespace-nowrap">{{ value }}</div>
        <div v-if="valueChange" class="text-xs">
            <value-change :value="valueChange" />
        </div>
    </div>
</template>