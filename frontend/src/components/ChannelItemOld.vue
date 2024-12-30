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
    <div class="grid grid-cols-[80px_60px_1fr]  gap-1 hover:bg-gray-200 my-1 border border-blue-300 rounded shadow">
        <!-- class="grid grid-cols-[80px_60px_1fr] lg:grid-cols-[80px_60px_2fr_1fr] gap-1 hover:bg-gray-200 my-1 border border-blue-300 rounded shadow"> -->
        <!-- 1 коллонка: Место -->
        <div class="col-span-1 flex flex-nowrap space-x-2  items-center">
            <!-- <div class="text-l flex flex-nowrap space-x-2 items-center"> -->
            <div class="font-bold min-w-4 text-right">{{ item.rank }}</div>
            <div class="min-w-8 text-center text-sm ">
                (<value-change :value="item.rank_change" />)
            </div>
            <!-- </div> -->
        </div>
        <!-- 2 коллонка: лого -->
        <div class="flex items-center ">
            <img class="h-8 " :src="channelThumbnail(item)" :alt="item.channel_title" />
        </div>
        <!-- 3 Канал и метрики -->
        <div class="col-span-1">
            <div>
                <div class="flex-row text-xl ">
                    <div class="md:flex flex-row justify-between items-center">
                        <!-- Channel title -->
                        <div class="" :title="item.description">
                            <span @click="showDetails = !showDetails"
                                class=" text-gray-300 cursor-pointer hover:text-black mr-1 select-none">{{ showDetails ?
                                    '▼' : '►'
                                }}</span>
                            <a target="_blank" class="hover:underline"
                                :href="'https://www.youtube.com/' + item.custom_url">
                                {{ item.channel_title }}
                            </a>
                        </div>
                        <!-- Метрики -->
                        <div class="min-w-80">
                            <stat-block class="text-sm" :stat="item.stat" />
                        </div>
                    </div>
                    <!-- Top video -->
                    <div v-if="showDetails" class="text-xs items-center">
                        <div v-for="(video, index) in item.top_videos " :key="video.video_id">
                            <video-info :video="video" :index="index" />
                        </div>
                    </div>

                </div>
            </div>
        </div>
        <!-- 4 Horizontal Bars -->
        <!-- <div class="col-span-1">
            <bar-block :stat="item.stat" :scale="props.scale" />
        </div> -->
    </div>



</template>