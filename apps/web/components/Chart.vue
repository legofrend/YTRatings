<script setup>
import { computed } from 'vue';
import ChannelItem from './ChannelItem.vue';

const props = defineProps({
  data: { type: Object, required: true },
  selectedSort: { type: String, default: 'rank' },
  period: { type: String, default: null },
  /** Page size (= selected top N). */
  limit: { type: Number, default: 20 },
  /** 1-based page index. */
  page: { type: Number, default: 1 },
  /** Total ranked channels (from API). Falls back to loaded length. */
  total: { type: Number, default: null },
  /** Client-side filter by title / custom_url; empty = no filter. */
  filterQuery: { type: String, default: '' },
  pageCategoryId: { type: Number, default: null },
  /** category_id → sys_name for ChannelItem links. */
  categorySysById: { type: Object, default: () => ({}) },
  showHelp: { type: Boolean, default: false },
  loadingMore: { type: Boolean, default: false },
});

const emit = defineEmits(['change-page']);

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

const pageSize = computed(() => Math.max(1, props.limit || 20));

/** When filtering locally, page over filtered loaded set; else use API total. */
const effectiveTotal = computed(() => {
  if (filterActive.value) return sortetChannels.value.length;
  if (props.total != null && props.total > 0) return props.total;
  return sortetChannels.value.length;
});

const totalPages = computed(() => {
  const n = effectiveTotal.value;
  if (!n) return 1;
  return Math.max(1, Math.ceil(n / pageSize.value));
});

const currentPage = computed(() => {
  const p = Math.floor(Number(props.page) || 1);
  return Math.min(Math.max(1, p), totalPages.value);
});

const pageChannels = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return sortetChannels.value.slice(start, start + pageSize.value);
});

/** Compact page number list with ellipsis when many pages. */
const pageItems = computed(() => {
  const total = totalPages.value;
  const cur = currentPage.value;
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const items = [];
  const push = (v) => {
    if (items[items.length - 1] !== v) items.push(v);
  };
  push(1);
  const lo = Math.max(2, cur - 1);
  const hi = Math.min(total - 1, cur + 1);
  if (lo > 2) push('…');
  for (let i = lo; i <= hi; i++) push(i);
  if (hi < total - 1) push('…');
  push(total);
  return items;
});

function go(p) {
  const n = Math.min(Math.max(1, p), totalPages.value);
  if (n === currentPage.value) return;
  emit('change-page', n);
}
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
        Ничего не найдено в загруженных каналах.
        Enter — поиск по всем каналам категории
      </p>
      <ul v-auto-animate class="pl-5 md:pl-8 min-w-0">
        <li
          v-for="(item, index) in pageChannels"
          :key="item.channel_id"
          class="min-w-0"
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

      <p v-if="loadingMore" class="text-center text-sm text-white/60 py-2">
        Загрузка…
      </p>

      <nav
        v-if="totalPages > 1"
        class="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-4 py-4 text-sm text-white/90 select-none"
        aria-label="Страницы рейтинга"
      >
        <button
          type="button"
          class="px-2 py-1 rounded disabled:opacity-30 hover:bg-white/10"
          :disabled="currentPage <= 1"
          aria-label="Предыдущая страница"
          @click="go(currentPage - 1)"
        >
          ←
        </button>

        <div class="flex flex-wrap items-center justify-center gap-1">
          <template v-for="(item, i) in pageItems" :key="`${item}-${i}`">
            <span v-if="item === '…'" class="px-1 opacity-50">…</span>
            <button
              v-else
              type="button"
              class="min-w-8 px-2 py-1 rounded"
              :class="
                item === currentPage
                  ? 'bg-white text-black font-semibold'
                  : 'hover:bg-white/10'
              "
              :aria-current="item === currentPage ? 'page' : undefined"
              @click="go(item)"
            >
              {{ item }}
            </button>
          </template>
        </div>

        <button
          type="button"
          class="px-2 py-1 rounded disabled:opacity-30 hover:bg-white/10"
          :disabled="currentPage >= totalPages"
          aria-label="Следующая страница"
          @click="go(currentPage + 1)"
        >
          →
        </button>

        <span class="text-xs text-white/60 sm:ml-1">
          {{ currentPage }} / {{ totalPages }}
        </span>
      </nav>
    </main>
  </div>
</template>
