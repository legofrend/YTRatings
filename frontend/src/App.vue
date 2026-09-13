<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import axios from 'axios';
import Chart from './components/Chart.vue';
import InfoBlock from './components/InfoBlock.vue';
import FeedbackForm from './components/FeedbackForm.vue';

const categories = ref([]);
const periods = ref([]);
const data = ref({ category: null, period: null, scale: 0, data: [] });
const selectedSort = ref('rank');
const selectedCategoryId = ref(1);
const selectedPeriod = ref(null);
const loading = ref(true);
const error = ref(null);

const sortTypes = [
  { id: 'rank', name: 'Место' },
  { id: 'subscriber_count', name: 'Подписчики' },
  { id: 'like_share', name: 'Доля лайков' },
  { id: 'comment_share', name: 'Доля комментариев' },
  { id: 'duration', name: 'Длительность' },
];

const currentCategory = computed(() =>
  categories.value.find((c) => c.id === selectedCategoryId.value) || null
);

function formattedDate(dateStr) {
  if (!dateStr) return '';
  const dateObject = new Date(dateStr);
  const months = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
  ];
  return `${months[dateObject.getMonth()]} ${dateObject.getFullYear()}`;
}

/** Map flat channel_stat row → old report channel shape (UI expects nested `stat`). */
function mapChannel(ch) {
  const viewCount = ch.pv_view || 0;
  const likeShare = viewCount > 0 ? (ch.pv_like || 0) / viewCount * 100 : 0;
  const commentShare = viewCount > 0 ? (ch.pv_comment || 0) / viewCount * 100 : 0;

  return {
    channel_id: ch.channel_id,
    channel_title: ch.channel_title,
    description: ch.description || '',
    custom_url: ch.custom_url,
    thumbnail_url: ch.thumbnail_url,
    category_id: ch.category_id,
    rank: ch.rank,
    rank_change: ch.rank_change != null ? -ch.rank_change : 0, // denorm: + = worse; UI: + = better
    top_videos: null, // lazy
    videos_loading: false,
    videos_error: null,
    history: null, // lazy /channel dynamics
    history_loading: false,
    history_error: null,
    stat: {
      videos: ch.pv_video_long,
      video_clickbaits: null,
      shorts: ch.pv_video_short,
      duration: ch.pv_duration || 0,
      score: ch.pv_score,
      score_change: ch.pv_score_change,
      view_count: ch.pv_view,
      view_count_new_video: ch.pv_view_new_long,
      view_count_new_short: ch.pv_view_new_short,
      view_count_old_video: ch.pv_view_old_long,
      view_count_old_short: ch.pv_view_old_short,
      total_view_count_change: ch.pc_view,
      view_count_check: null,
      like_count: ch.pv_like,
      comment_count: ch.pv_comment,
      subscriber_count: ch.subscriber_count,
      subscriber_count_change: ch.pc_subscriber,
      like_share: likeShare,
      comment_share: commentShare,
    },
  };
}

async function fetchCategories() {
  const { data: rows } = await axios.get('categories');
  categories.value = rows;
}

async function fetchPeriods(categoryId) {
  const { data: res } = await axios.get('periods', {
    params: { category_id: categoryId },
  });
  // API: newest first
  periods.value = res.periods || [];
  return periods.value;
}

async function fetchChannels(categoryId, period, limit = 100) {
  const params = { category_id: categoryId, limit };
  if (period) params.period = period;

  const { data: res } = await axios.get('channels', { params });
  const channels = (res.channels || []).map(mapChannel);
  const top = channels[0];
  const scale = top
    ? top.stat.score + Math.max(0, -(top.stat.score_change || 0))
    : 0;

  selectedPeriod.value = res.period;
  data.value = {
    category: currentCategory.value,
    period: res.period,
    scale,
    data: channels,
  };
}

async function loadCategory(categoryId, preferredPeriod = null) {
  selectedCategoryId.value = Number(categoryId);
  const list = await fetchPeriods(selectedCategoryId.value);
  if (!list.length) {
    throw new Error('Нет периодов для категории');
  }

  let period = preferredPeriod;
  if (!period || !list.includes(period)) {
    period = list[0]; // latest
  }
  selectedPeriod.value = period;
  await fetchChannels(selectedCategoryId.value, period);
}

async function changeCategory(categoryId) {
  try {
    error.value = null;
    loading.value = true;
    await loadCategory(categoryId, selectedPeriod.value);
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}

async function changePeriod(period) {
  if (!period || period === selectedPeriod.value) return;
  try {
    error.value = null;
    loading.value = true;
    selectedPeriod.value = period;
    await fetchChannels(selectedCategoryId.value, period);
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}

function shiftPeriod(delta) {
  const idx = periods.value.indexOf(selectedPeriod.value);
  if (idx < 0) return;
  // periods newest-first: -1 = older, +1 = newer
  const next = idx - delta;
  if (next < 0 || next >= periods.value.length) return;
  changePeriod(periods.value[next]);
}

watch(selectedCategoryId, (id) => {
  if (id != null) localStorage.setItem('currentCategoryId', String(id));
});

async function initialize() {
  loading.value = true;
  error.value = null;
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const paramValue = urlParams.get('category_id');
    const localId = localStorage.getItem('currentCategoryId');
    const categoryId = paramValue
      ? Number(paramValue)
      : localId
        ? Number(localId)
        : 1;

    await fetchCategories();
    if (!categories.value.find((c) => c.id === categoryId)) {
      throw new Error('Категория не найдена');
    }
    await loadCategory(categoryId);
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  // v2 API; vite proxies /api → local FastAPI in dev
  axios.defaults.baseURL = `${window.location.origin}/api/ytr/v2/`;
  axios.defaults.withCredentials = true;
  initialize();
});
</script>

<template>
  <div class="mx-auto px-2 max-w-screen-lg">
    <h1 class="flex flex-wrap items-center justify-center gap-2 text-xl md:text-4xl my-3 ">Рейтинг
      <img class="h-6 md:h-8" src="/img/youtube_logo_black.svg" alt="">
      каналов
    </h1>
    <p v-if="loading">Loading...</p>
    <p v-else-if="error">{{ error }}</p>
    <div v-else>

      <div class="flex flex-col md:flex-row justify-center items-center shadow select-none gap-1 md:gap-5">
        <select
          :value="selectedCategoryId"
          @change="changeCategory($event.target.value)"
          name="category"
          class="pl-1 text-black text-base cursor-pointer rounded"
        >
          <option
            class="text-left"
            v-for="category in categories"
            :key="category.id"
            :value="category.id"
          >
            {{ category.name }}
          </option>
        </select>

        <div class="flex justify-center items-center select-none gap-1">
          <img
            src="/img/arrowLeftWhite.svg"
            class="h-4 mx-1 cursor-pointer"
            @click="shiftPeriod(-1)"
          />
          <select
            :value="selectedPeriod"
            @change="changePeriod($event.target.value)"
            name="period"
            class="text-black text-base cursor-pointer rounded"
          >
            <option
              v-for="p in periods"
              :key="p"
              :value="p"
            >
              {{ formattedDate(p) }}
            </option>
          </select>
          <img
            src="/img/arrowLeftWhite.svg"
            class="h-4 mx-1 cursor-pointer rotate-180"
            @click="shiftPeriod(1)"
          />
        </div>

        <div class="flex flex-row items-center gap-1">
          <div class="bg-white rounded-lg h-5 w-7 items-center flex justify-center">
            <img src="/img/sortBtn.svg" class="h-4" />
          </div>
          <div>
            <select
              v-model="selectedSort"
              name="sort"
              class="text-black cursor-pointer rounded"
            >
              <option
                class="text-left"
                v-for="sort in sortTypes"
                :key="sort.id"
                :value="sort.id"
              >
                {{ sort.name }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <h2 class="text-center text-xl md:text-3xl my-3">{{ data.category?.title || data.category?.name }}</h2>

      <Chart :data="data" :selected-sort="selectedSort" :period="selectedPeriod" />

      <info-block header="Методика" class="text-xs mt-10">
        Рейтинг на основе суммы просмотров на канале по видео и
        клипам двух последних месяцев. Клипы (shorts) учитываются с коэффициентом 1/10.
        <p>Критерии выбора каналов: {{ data.category?.description }}</p>
      </info-block>
    </div>
    <info-block header="Предложить свой канал или тему" class="text-lg mt-3">
      <feedback-form />
    </info-block>
  </div>
</template>
