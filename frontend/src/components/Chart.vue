<script setup>
import { ref } from 'vue';
import ChannelItem from './ChannelItem.vue';
const props = defineProps(['data'])

const showNumber = ref(10)

console.log(props.data)

</script>

<template>
    <div>
        <header
            class="grid grid-cols-[60px_40px_1fr] lg:grid-cols-[60px_40px_2fr_1fr] gap-1 text-xl border-b-2 border-black space-x-6">
            <div class="col-span-1">Место</div>
            <div class="col-span-2 flex justify-between"><span>Канал</span><span>Метрики</span></div>
            <div class="hidden lg:block col-span-1">Диаграмма</div>
        </header>

        <main>
            <ul v-auto-animate>
                <li v-for="item in data.data.slice(0, showNumber)" :key="item.rank">
                    <ChannelItem :item="item" :scale="props.data.scale" />
                </li>
            </ul>
        </main>
        <div class="text-2xl flex justify-center mx-3 select-none">
            <div class="cursor-pointer" @click="showNumber += showNumber < data.data.length ? 10 : 0">⏬</div>
            <div class="cursor-pointer" @click="showNumber = Math.max(showNumber - 10, 10)">⏫</div>
        </div>

    </div>
    <!-- class="grid grid-cols-4 gap-4 border border-blue-700" -->
</template>
