<script setup>
import ValueChange from './UI/ValueChange.vue';
import StatBlock from './StatBlock.vue';
import BarBlock from './BarBlock.vue';
import VideoInfo from './VideoInfo.vue';
import { ref } from 'vue';

const props = defineProps(['item', 'scale'])

const showDetails = ref(false);

function channelThumbnail(ch) {
    return ch.thumbnail_url ? ch.thumbnail_url : ('img/' + ch.channel_id + '.jpg')
}

// console.log(props.item)

// ⬆⬇ ► ▼ ▲ ⏬⏫ ⮜⮞➪➯ ➜ 👍 👁🕶😎👁️👀 👤𖹭❤️𖨆 💬.🗨️🗨

</script>
<template>

    <div>


        <div
            class="flex items-center bg-white text-black shadow-md  w-full min-w-fit my-2 mx-auto rounded-lg p-1 space-x-1 md:space-x-4">
            <!-- Left Column -->
            <div class="flex flex-col items-center">
                <div
                    class="flex justify-center items-center bg-green-500 text-white font-bold text-base w-5 h-5 rounded-md md:w-8 md:h-8 md:text-lg md:rounded-lg ">
                    {{ item.rank }}
                </div>
                <div v-show="item.rank_change"
                    class="relative mt-1 text-xs md:text-sm md:border border-dashed  rounded-lg p-0.5 flex justify-center items-center"
                    :class="item.rank_change > 0 ? 'border-green-500' : 'border-red-500'">
                    <value-change :value="item.rank_change" />
                </div>
            </div>

            <!-- Channel logo -->
            <img class="h-10 md:h-16 rounded-sm border border-gray-300" :src="channelThumbnail(item)"
                :alt="item.channel_title" />

            <div class="flex justify-between flex-col md:flex-row w-full">
                <!-- Channel title -->
                <div class="">
                    <div class="flex items-center" :title="item.description">
                        <div :class="showDetails ? 'rotate-90 ' : 'rotate-0'" class="bg-gray-50 p-1 select-none">
                            <img @click="showDetails = !showDetails" class="cursor-pointer mr-1 "
                                src="/img/arrowPeekRight.svg" alt="Показать топ видео канала">
                        </div>
                        <a target="_blank" class="hover:underline text-base md:text-lg font-semibold ml-1"
                            :href="'https://www.youtube.com/' + item.custom_url">
                            {{ item.channel_title }}
                        </a>
                    </div>

                </div>

                <!-- Stats -->
                <div class="min-w-fit">
                    <stat-block class="text-sm" :stat="item.stat" />
                </div>
            </div>
        </div>
        <div v-if="showDetails"
            class="text-xs w-auto p-1 ml-5 md:ml-32  -mt-4 shadow-lg bg-gray-50 rounded-lg text-black">
            <div class="flex flex-col" v-for="(video, index) in item.top_videos " :key="video.video_id">
                <video-info :video="video" :index="index" />
            </div>
        </div>
    </div>


</template>