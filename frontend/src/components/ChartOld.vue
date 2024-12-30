<script setup>
import { ref } from 'vue';
import ChannelItem from './ChannelItem.vue';
import ChannelItemNew from './ChannelItemNew.vue';
const props = defineProps(['data'])

const showNumber = ref(10)

// console.log(props.data)

</script>

<template>
    <div>
        <header class="grid grid-cols-[60px_40px_1fr]  gap-1 text-xl border-b-2 border-black space-x-6">
            <!-- class="grid grid-cols-[60px_40px_1fr] lg:grid-cols-[60px_40px_2fr_1fr] gap-1 text-xl border-b-2 border-black space-x-6"> -->
            <div class="col-span-1">Место</div>
            <div class="col-span-2 flex justify-between"><span>Канал</span><span>Метрики</span></div>
            <!-- <div class="hidden lg:block col-span-1">Диаграмма</div> -->
        </header>

        <main>
            <ul v-auto-animate>
                <li v-for="item in data.data.slice(0, showNumber)" :key="item.rank">
                    <!-- <ChannelItem :item="item" :scale="props.data.scale" /> -->
                    <ChannelItemNew />
                </li>
            </ul>
        </main>
        <div class="text-xl flex justify-center mt-3 gap-3 select-none">
            <button class="border border-gray-300 shadow px-2 rounded"
                @click="showNumber += showNumber < data.data.length ? 10 : 0">Больше</button>
            <!-- ⏬⏫ -->
            <button class="border border-gray-300 px-2 rounded shadow"
                @click="showNumber = Math.max(showNumber - 10, 10)">Меньше</button>
        </div>

    </div>
    <!-- class="grid grid-cols-4 gap-4 border border-blue-700" -->
</template>
