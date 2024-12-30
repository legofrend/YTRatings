<script setup>
import { ref, computed } from 'vue';
import ChannelItem from './ChannelItem.vue';
const props = defineProps(['data', 'selectedSort'])

const showNumber = ref(10)


// console.log(props.data)
const topNumbers = [
    { "value": 10, "name": "топ 10" },
    { "value": 20, "name": "топ 20" },
    { "value": 100, "name": "все" },
]

const sortetChannels = computed(() => {
    const sortOrder = -1
    const channels = props.data.data.slice(0, showNumber.value)
    if (props.selectedSort == 'rank' || props.selectedSort == null) { return channels }

    return [...channels].sort((item1, item2) => {
        const value1 = item1.stat[props.selectedSort];
        const value2 = item2.stat[props.selectedSort];
        if (typeof value1 === 'number' && typeof value2 === 'number') {
            // Сравнение для чисел
            return (value1 - value2) * sortOrder;
        } else if (typeof value1 === 'string' && typeof value2 === 'string') {
            // Сравнение для строк
            return value1.localeCompare(value2) * sortOrder;
        }

        return 0;
    });
})

</script>

<template>
    <div>
        <header class=" hidden grid grid-cols-[60px_200px_1fr]  gap-1 text-xl border-b-2 border-black space-x-6">
            <!-- class="grid grid-cols-[60px_40px_1fr] lg:grid-cols-[60px_40px_2fr_1fr] gap-1 text-xl border-b-2 border-black space-x-6"> -->
            <div class="col-span-1">Место</div>
            <div class="col-span-1">Канал </div>
            <div class="col-span-1">Метрики</div>
            <!-- <div class="hidden lg:block col-span-1">Диаграмма</div> -->
        </header>

        <main>
            <ul v-auto-animate>
                <li v-for="item in sortetChannels" :key="item.rank">
                    <ChannelItem :item="item" :scale="props.data.scale" />
                </li>
            </ul>
        </main>
        <div class=" flex justify-center  ">
            <select v-model="showNumber" @change="showNumber = $event.target.value" name="topChannels"
                class=" text-black text-base m-3 cursor-pointer rounded">
                <option class="" v-for="n in topNumbers" :key="n.value" :value="n.value">{{
                    n.name }}
                </option>
            </select>
        </div>
        <!-- <div class="text-xl flex justify-center mt-3 gap-3 select-none">
            <button class="border border-gray-300 shadow px-2 rounded"
                @click="showNumber += showNumber < data.data.length ? 10 : 0">Больше</button>
            <button class="border border-gray-300 px-2 rounded shadow"
                @click="showNumber = Math.max(showNumber - 10, 10)">Меньше</button>
        </div> -->

    </div>
    <!-- class="grid grid-cols-4 gap-4 border border-blue-700" -->
</template>
