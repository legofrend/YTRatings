<script setup>
import { computed } from 'vue';
import ValueChange from './ValueChange.vue';
const props = defineProps(['value', 'valueChange', 'title', 'type'])

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
    if (props.type === 'time') {
        return 'bg-black text-white w-8'
    } else if (props.type == 'views' || props.type == 'subscribers') {
        return 'bg-blue-50 w-10'
    } else {
        return 'bg-blue-50 w-8'
    }
})
</script>

<template>
    <div class="flex flex-col  px-2 py-1 items-center rounded-md shadow-md" :class="style" :title="title">
        <img :src="image[type]" class="h-4 mb-1" alt="">
        <div>{{ value }}</div>
        <div v-if="valueChange" class="text-xs">
            <value-change :value="valueChange" />
        </div>
    </div>
</template>