<script setup>
import { ref } from 'vue';
import StatVideoBlock from './StatVideoBlock.vue';

const props = defineProps(['video', 'index'])
const isThumbnailVisible = ref(false)
const emojiNumbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

function formattedDate(dateStr) {
    const dateObject = new Date(dateStr);
    const day = String(dateObject.getDate()).padStart(2, '0');
    const month = String(dateObject.getMonth() + 1).padStart(2, '0');
    return `${day}.${month}`;
}

</script>

<template>
    <div class="flex  flex-col gap-1 my-1">
        <div class="flex items-center gap-1 ml-1">
            <div class="bg-green-500 rounded-sm px-1 text-xs"> {{ index + 1 }}</div>

            <div class="hover:underline relative" @mouseover="isThumbnailVisible = true"
                @mouseleave="isThumbnailVisible = false">
                <a :href="video.video_url" target="_blank" :title="video.title">
                    {{ video.title }}
                </a>
                <img v-if="isThumbnailVisible" :src="video.thumbnail_url" class="absolute w-80 z-10 left-8" alt="">
            </div>
            <div v-if="video.channel_title" class="text-xs text-gray-500 ml-1 shrink-0">
                · {{ video.channel_title }}
            </div>
            <div v-if="video.published_at" class="text-xs text-gray-500 ml-2 shrink-0">
                {{ formattedDate(video.published_at) }}
            </div>
        </div>
        <div class="flex ml-5 items-center border-t  border-gray-300">
            <div title="Клип" v-if="video.is_short" class="flex">
                <img class="h-3  mr-1" src="/img/iconShortColor.svg" alt="shorts">
            </div>

            <div title="Видео" v-else class="flex ">
                <img class="h-3  mr-1" src="/img/iconVideoColor.svg" alt="shorts">
            </div>
            <StatVideoBlock :stat="video.stat" />
            <div :title="video.clickbait_comment" class="flex cursor-help ml-1">
                <!-- <span v-if="video.is_clickbait">⚠️</span> -->
                <img v-if="video.is_clickbait" src="/img/iconClickbaitYellow.svg" class="h-4" />
                <!-- <img v-else src="/img/iconClickbait.svg" class="h-3" /> -->
            </div>
        </div>

    </div>

</template>