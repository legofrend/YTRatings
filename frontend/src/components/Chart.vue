<script setup>
import { ref, computed } from 'vue';
import ChannelItem from './ChannelItem.vue';

const props = defineProps({
  data: { type: Object, required: true },
  selectedSort: { type: String, default: 'rank' },
  period: { type: String, default: null },
});

const showNumber = ref(10);

const topNumbers = [
  { value: 10, name: 'топ 10' },
  { value: 20, name: 'топ 20' },
  { value: 100, name: 'все' },
];

const sortetChannels = computed(() => {
  const channels = (props.data.data || []).slice(0, showNumber.value);
  if (props.selectedSort == 'rank' || props.selectedSort == null) {
    return channels;
  }

  // higher is better for all non-rank metrics
  const sortOrder = -1;
  return [...channels].sort((item1, item2) => {
    const value1 = item1.stat[props.selectedSort];
    const value2 = item2.stat[props.selectedSort];
    if (typeof value1 === 'number' && typeof value2 === 'number') {
      return (value1 - value2) * sortOrder;
    }
    return 0;
  });
});
</script>

<template>
  <div>
    <header class="hidden grid grid-cols-[60px_200px_1fr] gap-1 text-xl border-b-2 border-black space-x-6">
      <div class="col-span-1">Место</div>
      <div class="col-span-1">Канал</div>
      <div class="col-span-1">Метрики</div>
    </header>

    <main>
      <ul v-auto-animate>
        <li v-for="item in sortetChannels" :key="item.channel_id">
          <ChannelItem :item="item" :scale="props.data.scale" :period="period" />
        </li>
      </ul>
    </main>
    <div class="flex justify-center">
      <select
        v-model.number="showNumber"
        name="topChannels"
        class="text-black text-base m-3 cursor-pointer rounded"
      >
        <option v-for="n in topNumbers" :key="n.value" :value="n.value">
          {{ n.name }}
        </option>
      </select>
    </div>
  </div>
</template>
