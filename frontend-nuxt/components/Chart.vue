<script setup>
import { computed } from 'vue';
import ChannelItem from './ChannelItem.vue';

const props = defineProps({
  data: { type: Object, required: true },
  selectedSort: { type: String, default: 'rank' },
  period: { type: String, default: null },
  limit: { type: Number, default: 20 },
  /** Client-side filter by title / custom_url; empty = no filter. */
  filterQuery: { type: String, default: '' },
  pageCategoryId: { type: Number, default: null },
  /** category_id → sys_name for ChannelItem links. */
  categorySysById: { type: Object, default: () => ({}) },
  showHelp: { type: Boolean, default: false },
});

function normHandle(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/^@+/, '');
}

const filterActive = computed(() => normHandle(props.filterQuery).length > 0);

const sortetChannels = computed(() => {
  let channels = [...(props.data.data || [])];

  const q = normHandle(props.filterQuery);
  if (q) {
    channels = channels.filter((c) => {
      const title = String(c.channel_title || '').toLowerCase();
      const handle = normHandle(c.custom_url);
      return title.includes(q) || handle.includes(q);
    });
  }

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
      <p
        v-if="filterActive && sortetChannels.length === 0"
        class="text-center text-sm text-gray-500 py-6"
      >
        Ничего не найдено в текущем топ-{{ Math.min(data.data?.length || 0, 100) }}.
        Enter — поиск по всем каналам категории
      </p>
      <ul v-auto-animate>
        <li
          v-for="(item, index) in sortetChannels"
          v-show="filterActive || limit >= 999 || index < limit"
          :key="item.channel_id"
        >
          <ChannelItem
            :item="item"
            :scale="props.data.scale"
            :period="period"
            :page-category-id="pageCategoryId"
            :category-sys-by-id="categorySysById"
            :help-arrow="showHelp && index === 0"
            :help-title="showHelp && index === 0"
            :help-rank="showHelp && index === 1"
          />
        </li>
      </ul>
    </main>
  </div>
</template>
