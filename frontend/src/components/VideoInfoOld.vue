<script setup>
import { ref } from 'vue';
import StatBlock from './StatBlock.vue';

const props = defineProps(['video', 'index'])
const isThumbnailVisible = ref(false)
const emojiNumbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

</script>

<template>
    <div class="md:flex flex-row justify-between gap-1 items-center border border-purple-300 my-1">
        <div class="flex items-center">
            {{ emojiNumbers[index] }}
            <div :title="video.clickbait_comment" v-if="video.is_clickbait" class="flex cursor-help">⚠️</div>
            <div title="Клип" v-if="video.is_short" class="flex"><img class="h-3  mr-1" src="/img/short.svg"
                    alt="shorts"></div>
            <div title="Видео" v-else class="flex "><img class="h-3  mr-1" src="/img/video.svg" alt="shorts">
            </div>

            <div class="hover:underline relative" @mouseover="isThumbnailVisible = true"
                @mouseleave="isThumbnailVisible = false">
                <a :href="video.video_url" target="_blank" :title="video.title">
                    {{ video.title }}
                </a>
                <img v-if="isThumbnailVisible" :src="video.thumbnail_url" class="absolute w-80 z-10" alt="">

            </div>
        </div>
        <div class="min-w-48 text-right">
            <StatBlock :stat="video.stat" />
        </div>
    </div>

</template>