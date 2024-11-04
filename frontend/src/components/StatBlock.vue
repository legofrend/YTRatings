<script setup>
import { computed } from 'vue';
import ValueChange from './UI/ValueChange.vue';

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

const likeShare = computed(() => {
    var val = Math.round((props.stat.like_count / props.stat.view_count * 100 * 10)) / 10
    return val.toFixed(1);
})

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 1) {
        return `${hours}ч`
    }
    return (hours > 0 ? `${hours}:` : '') + `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')} `;

}


// const totalPrice = computed(() => cart.value.reduce((acc, item) => acc + item.price, 0))
// const vatPrice = computed(() => Math.round((totalPrice.value * 5) / 100))

</script>

<template>
    <div class="flex flex-auto space-x-1 items-center">
        <div title="Взвешенные просмотры (клипы с коэф. 0.1)">👁{{ ValDisplay(stat.score) }}</div>
        <div v-if="stat.score_change">
            (<value-change :value="stat.score_change" />)
        </div>
        <div title="Отноешние Лайки/Просмотры">👍{{ likeShare }}%</div>
        <!-- <div title="Комментарии" v-if="stat.comment_count">🗨{{ ValDisplay(stat.comment_count) }}M</div> -->
        <div title="Подписчики" v-if="stat.subscriber_count">👤{{ ValDisplay(stat.subscriber_count) }}</div>
        <div title="Количество новых видео за месяц" v-if="stat.videos" class="flex items-center"><img class="h-3 mr-1"
                src="/img/video.svg" alt="videos"> {{ stat.videos - stat.shorts }}
        </div>
        <div title="Количество новых клипов за месяц" v-if="stat.shorts" class="flex items-center"><img
                class="h-3  mr-1" src="/img/short.svg" alt="shorts"> {{ stat.shorts }}
        </div>
        <div title="Длительность" v-if="stat.duration" class="bg-gray-800 text-white rounded px-1">{{
            formatTime(stat.duration) }}</div>

        <!-- "is_short": 0,
              "is_clickbait": 1,
              "clickbait_comment": "Заголовок использует драматургические элементы, заставляет задуматься о последствиях, что может вводить в заблуждение.",
              "duration": 60, -->

    </div>

</template>