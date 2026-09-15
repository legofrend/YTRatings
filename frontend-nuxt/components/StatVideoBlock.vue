<script setup>
import { computed } from 'vue';

const props = defineProps(['stat'])
// console.log(props.stat)

const ValDisplay = (value) => {
    if (Math.abs(value) >= 10 ** 6) {
        var val = (Math.round(value / 10 ** 6 * 10) / 10);
        return val.toFixed(1) + 'M';
    }
    if (Math.abs(value) >= 1000) {
        var val = (Math.round(value / 10 ** 3));
        return val.toFixed(0) + 'K';
    }
    return value
}

const scoreTitle = computed(() => {
    var val = ValDisplay(props.stat.score) + ' = ' + ValDisplay(props.stat.view_count_new_video) + ' + '
        + ValDisplay(props.stat.view_count_new_short) + ' /10 + ' + ValDisplay(props.stat.view_count_old_video) + ' + ' + ValDisplay(props.stat.view_count_old_short) + ' /10'

    return val;
})


const likeShare = computed(() => {
    var val = Math.round((props.stat.like_count / props.stat.view_count * 100 * 10)) / 10
    return val.toFixed(1);
})

const clickbaitShare = computed(() => {
    var val = Math.round((props.stat.video_clickbaits / props.stat.videos * 100))
    return val;
})

const commentShare = computed(() => {
    var val = Math.round((props.stat.comment_count / props.stat.view_count * 100 * 10)) / 10
    return val.toFixed(1);
})



function formatTime(seconds, full = false) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (full) {
        return (hours > 0 ? `${hours}:` : '') + `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')} `;
    }
    if (hours > 0) {
        return Math.round(seconds / 3600) + 'ч';
    }
    return `${minutes}м`

}


// const totalPrice = computed(() => cart.value.reduce((acc, item) => acc + item.price, 0))
// const vatPrice = computed(() => Math.round((totalPrice.value * 5) / 100))

</script>

<template>
    <div class="flex  space-x-2 text-xs">

        <div class="flex px-1 items-center">
            <img src="/img/iconView.svg" class="h-3  mr-1" alt="">
            <div>{{ ValDisplay(stat.view_count) }}</div>
        </div>
        <div class="flex px-1  items-center">
            <img src="/img/iconLike.svg" class="h-3  mr-1" alt="">
            <div>{{ likeShare + '%' }}</div>
        </div>
        <div class="flex px-1 items-center">
            <img src="/img/iconComment.svg" class="h-3 mr-1" alt="">
            <div>{{ commentShare + '%' }}</div>
        </div>
        <div class="flex px-1 items-center bg-black text-white rounded-md">
            <div>{{ formatTime(stat.duration, true) }}</div>
        </div>

    </div>

</template>