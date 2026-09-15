<script setup>
import { computed } from 'vue';
import ChannelItem from './ChannelItem.vue';

const props = defineProps({
  data: { type: Object, required: true },
  selectedSort: { type: String, default: 'rank' },
  period: { type: String, default: null },
  limit: { type: Number, default: 20 },
  showHelp: { type: Boolean, default: false },
});

const sortetChannels = computed(() => {
  const channels = [...(props.data.data || [])];
  if (props.selectedSort == 'rank' || props.selectedSort == null) {
    return channels;
  }

  const sortOrder = -1;
  return channels.sort((item1, item2) => {
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
        <li
          v-for="(item, index) in sortetChannels"
          v-show="limit >= 999 || index < limit"
          :key="item.channel_id"
        >
          <ChannelItem
            :item="item"
            :scale="props.data.scale"
            :period="period"
            :help-arrow="showHelp && index === 0"
            :help-title="showHelp && index === 0"
            :help-rank="showHelp && index === 1"
          />
        </li>
      </ul>
    </main>
  </div>
</template>
