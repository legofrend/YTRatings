<script setup>
import { computed } from 'vue';
import ValueChange from './UI/ValueChange.vue';
import dataBlock from './UI/dataBlock.vue';

const props = defineProps({
  stat: { type: Object, required: true },
  wide: { type: Boolean, default: false },
})
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
    var val = 'Индекс: ' + ValDisplay(props.stat.score) + ' = ' + ValDisplay(props.stat.view_count_new_video) + ' + '
        + ValDisplay(props.stat.view_count_new_short) + ' /10 + ' + ValDisplay(props.stat.view_count_old_video) + ' + ' + ValDisplay(props.stat.view_count_old_short) + ' /10' + '\n'
        + 'в среднем на 1 видео: ' + (props.stat.videos > 0
            ? ValDisplay(Math.round(props.stat.view_count_new_video / props.stat.videos))
            : '-')

    return val;
})

/** "x.x%" or "-" when denominator is missing/zero. */
function sharePct(num, den, digits = 1) {
    const n = Number(num)
    const d = Number(den)
    if (!Number.isFinite(n) || !Number.isFinite(d) || d <= 0) return '-'
    return (n / d * 100).toFixed(digits) + '%'
}

const likeShare = computed(() => sharePct(props.stat.like_count, props.stat.view_count))

const clickbaitShare = computed(() => sharePct(props.stat.video_clickbaits, props.stat.videos, 0))

const commentShare = computed(() => sharePct(props.stat.comment_count, props.stat.view_count))



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
    <div class="flex flex-auto flex-wrap gap-1 md:gap-2 items-baseline text-sm">
        <data-block :wide="wide" type="score" :value="ValDisplay(stat.score)" :value-change="stat.score_change"
            :title="scoreTitle"></data-block>
        <data-block :wide="wide" type="subscribers" :value="ValDisplay(stat.subscriber_count)"
            :value-change="stat.subscriber_count_change" title="Подписчики"></data-block>
        <data-block :wide="wide" type="likes" :value="likeShare" title="Отношение Лайки/Просмотры"></data-block>
        <data-block :wide="wide" type="comments" :value="commentShare"
            title="Отношение количества комментариев к просмотрам"></data-block>

        <data-block :wide="wide" type="videos" :value="stat.videos" title="Количество новых видео за месяц"></data-block>
        <data-block :wide="wide" type="shorts" :value="stat.shorts" title="Количество новых клипов за месяц"></data-block>
        <data-block :wide="wide" class="hidden md:flex" type="time" :value="formatTime(stat.duration)"
            title="Длительность"></data-block>

        <!-- 
        <div title="Комментарии" v-if="stat.comment_count">🗨{{ ValDisplay(stat.comment_count) }}M</div> 
        <data-block type="clickbaits" :value="clickbaitShare" title="Доля кликбейтных названий"></data-block>
         
        -->


    </div>

</template>