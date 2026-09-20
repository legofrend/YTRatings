<script setup>
import ValueChange from './UI/ValueChange.vue';
import StatBlock from './StatBlock.vue';
import VideoInfo from './VideoInfo.vue';
import ChannelHistory from './ChannelHistory.vue';
import { ref, watch, computed } from 'vue';
import { mapVideo } from '~/utils/report';

const props = defineProps({
    item: { type: Object, required: true },
    scale: { type: [Number, String], default: 0 },
    period: { type: String, default: null },
    /** Which help bubbles to show on this row. */
    helpRank: { type: Boolean, default: false },
    helpArrow: { type: Boolean, default: false },
    helpTitle: { type: Boolean, default: false },
});

const { videos: fetchVideos, channelDynamics } = useYtrApi();
const VIDEOS_STEP = 5;
const VIDEOS_MAX = 20;

const showDetails = ref(false);
const copied = ref(false);
const copiedLabel = ref('ID скопирован');
/** How many top videos to show (5 → 10 → 15 → 20). Fetch always pulls VIDEOS_MAX. */
const videosLimit = ref(VIDEOS_STEP);
const EMPTY_LOGO = '/img/empty.png';
const logoImg = ref(null);
const logoSrc = ref(localLogo(props.item) || props.item?.thumbnail_url || EMPTY_LOGO);
const visibleVideos = computed(() => {
  const list = props.item.top_videos || [];
  return list.slice(0, videosLimit.value);
});
const canExpandVideos = computed(() => {
  const n = props.item.top_videos?.length || 0;
  return videosLimit.value < Math.min(VIDEOS_MAX, n);
});

function localLogo(ch) {
  // absolute — иначе на вложенных URL уезжает в относительный путь
  if (!ch?.custom_url) return '';
  return `/channel_logo/${encodeURIComponent(ch.custom_url)}.jpg`;
}

function onLogoError() {
  const yt = props.item?.thumbnail_url;
  if (yt && logoSrc.value !== yt && logoSrc.value !== EMPTY_LOGO) {
    logoSrc.value = yt;
    return;
  }
  if (logoSrc.value !== EMPTY_LOGO) {
    logoSrc.value = EMPTY_LOGO;
  }
}

/** SSG: img may 404 before Vue hydrates and @error is missed. */
onMounted(() => {
  const el = logoImg.value;
  if (el && el.complete && el.naturalWidth === 0) onLogoError();
});

watch(
  () => props.item.channel_id,
  () => {
    logoSrc.value = localLogo(props.item) || props.item?.thumbnail_url || EMPTY_LOGO;
  }
);

/** Prefer @handle; fall back to UC… id when custom_url missing. */
function channelRef() {
  const handle = (props.item.custom_url || '').trim();
  return handle || props.item.channel_id;
}

/** JSONL row for `python -m app.main edit-channels --file …` (null = leave unchanged). */
function editTemplateLine() {
  const ref = channelRef();
  const isHandle = ref !== props.item.channel_id;
  return JSON.stringify({
    ...(isHandle ? { id: ref } : { channel_id: ref }),
    category_id: props.item.category_id ?? null,
    status: null,
    priority: null,
  });
}

async function copyEditTemplate() {
  const line = editTemplateLine();
  try {
    await navigator.clipboard.writeText(line);
    copiedLabel.value = 'шаблон edit скопирован';
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    window.prompt('edit-channels JSONL', line);
  }
}

function onLogoClick(e) {
  // Admin-only: Shift+click → JSONL edit row (@handle preferred); plain click does nothing
  if (!e.shiftKey) return;
  e.preventDefault();
  copyEditTemplate();
}

async function loadVideos() {
  if (!props.period) return;
  // already pulled max (or confirmed fewer exist) for this open/period
  if (props.item.videos_loaded_max && !props.item.videos_loading) return;
  if (
    props.item.top_videos != null &&
    props.item.top_videos.length >= VIDEOS_MAX &&
    !props.item.videos_loading
  ) {
    props.item.videos_loaded_max = true;
    return;
  }
  if (props.item.videos_loading) return;

  props.item.videos_loading = true;
  props.item.videos_error = null;
  try {
    // one shot: fetch max, UI reveals by VIDEOS_STEP
    const res = await fetchVideos(props.item.channel_id, props.period, VIDEOS_MAX);
    props.item.top_videos = (res.videos || []).map(mapVideo);
    props.item.videos_loaded_max = true;
  } catch (err) {
    props.item.videos_error = err.message || String(err);
    props.item.top_videos = [];
  } finally {
    props.item.videos_loading = false;
  }
}

function expandVideos() {
  videosLimit.value = Math.min(videosLimit.value + VIDEOS_STEP, VIDEOS_MAX);
}

async function loadHistory() {
  if (props.item.history != null || props.item.history_loading) return;

  props.item.history_loading = true;
  props.item.history_error = null;
  try {
    const res = await channelDynamics(props.item.channel_id, 12);
    props.item.history = res.points || [];
  } catch (err) {
    props.item.history_error = err.message || String(err);
    props.item.history = [];
  } finally {
    props.item.history_loading = false;
  }
}

async function toggleDetails() {
  showDetails.value = !showDetails.value;
  if (!showDetails.value) return;

  videosLimit.value = VIDEOS_STEP;
  await loadVideos();
  await loadHistory();
}

watch(
  () => props.period,
  () => {
    // Parent remaps channels (with/without preload). Don't wipe preloaded top_videos.
    videosLimit.value = VIDEOS_STEP;
    props.item.videos_loaded_max = false;
    if (showDetails.value) {
      loadVideos().then(() => loadHistory());
    }
  }
);
</script>

<template>
  <div class="relative">
    <div
      class="flex items-center bg-white text-black shadow-md w-full min-w-fit my-2 mx-auto rounded-lg p-1 space-x-1 md:space-x-4"
    >
      <div class="flex flex-col items-center">
        <div
          class="flex justify-center items-center bg-green-500 text-white font-bold text-base w-5 h-5 rounded-md md:w-8 md:h-8 md:text-lg md:rounded-lg"
        >
          {{ item.rank }}
        </div>
        <div
          v-show="item.rank_change"
          class="relative mt-1 text-xs md:text-sm md:border border-dashed rounded-lg p-0.5 flex justify-center items-center"
          :class="item.rank_change > 0 ? 'border-green-500' : 'border-red-500'"
        >
          <value-change :value="item.rank_change" />
        </div>
      </div>

      <div class="relative h-10 w-10 md:h-16 md:w-16 shrink-0 overflow-hidden rounded-sm border border-gray-300">
        <img
          ref="logoImg"
          class="h-full w-full max-w-none object-cover cursor-pointer hover:opacity-80"
          :src="logoSrc"
          :alt="item.channel_title"
          :title="'Shift+клик — JSONL (@handle)\n' + item.channel_title + '\n' + (item.custom_url || item.channel_id)"
          @error="onLogoError"
          @click="onLogoClick"
        />
        <div
          v-if="copied"
          class="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] bg-black text-white px-1.5 py-0.5 rounded z-10"
        >
          {{ copiedLabel }}
        </div>
      </div>

      <div class="flex justify-between flex-col md:flex-row w-full">
        <div>
          <div class="flex items-center relative" :title="item.description">
            <div class="relative">
              <div :class="showDetails ? 'rotate-90 ' : 'rotate-0'" class="bg-gray-50 p-1 select-none">
                <img
                  @click="toggleDetails"
                  class="cursor-pointer mr-1"
                  src="/img/arrowPeekRight.svg"
                  alt="Показать топ видео канала"
                />
              </div>
              <div
                v-if="helpArrow"
                class="absolute left-0 top-full mt-2 z-50 w-52 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
                @click.stop
              >
                Нажмите, чтобы посмотреть топ видео канала за месяц и динамику просмотров
              </div>
            </div>
            <a
              target="_blank"
              class="relative hover:underline text-base md:text-lg font-semibold ml-1"
              :href="'https://www.youtube.com/' + item.custom_url"
            >
              {{ item.channel_title }}
              <span
                v-if="helpTitle"
                class="absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50 block w-48 whitespace-normal font-normal rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300 no-underline"
                @click.stop
              >
                Нажмите, чтобы открыть YouTube канала в отдельном окне
              </span>
            </a>
          </div>
        </div>

        <div class="min-w-fit">
          <stat-block class="text-sm" :stat="item.stat" />
        </div>
      </div>
    </div>

    <div
      v-if="helpRank"
      class="absolute left-0 top-full z-50 w-56 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300 -mt-1"
      @click.stop
    >
      Изменение канала в рейтинге по сравнению с прошлым месяцем
    </div>

    <div
      v-if="showDetails"
      class="text-xs w-auto p-2 ml-5 md:ml-32 -mt-4 shadow-lg bg-gray-50 rounded-lg text-black"
    >
      <div
        v-if="item.videos_loading && !item.top_videos?.length"
        class="flex items-center gap-2 p-3 text-gray-500"
      >
        <span
          class="inline-block h-5 w-5 rounded-full border-2 border-gray-300 border-t-blue-500 animate-spin"
        />
        Загрузка видео…
      </div>
      <div v-else-if="item.videos_error" class="p-2 text-red-600">{{ item.videos_error }}</div>
      <div v-else-if="!item.top_videos?.length" class="p-2 text-gray-500">Нет новых видео за период</div>
      <div v-else>
        <div
          class="flex flex-col"
          v-for="(video, index) in visibleVideos"
          :key="video.video_id"
        >
          <video-info :video="video" :index="index" />
        </div>
        <button
          v-if="canExpandVideos"
          type="button"
          class="mt-1 mb-0.5 mx-auto block px-2 py-0.5 text-xs text-gray-500 hover:text-black hover:underline"
          title="Показать ещё 5 видео"
          @click="expandVideos"
        >
          еще 5
        </button>
      </div>

      <ChannelHistory
        v-if="item.history != null || item.history_loading || item.history_error"
        :points="item.history || []"
        :loading="item.history_loading"
        :error="item.history_error"
      />
    </div>
  </div>
</template>
