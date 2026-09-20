<script setup>
import axios from 'axios';
import ValueChange from './UI/ValueChange.vue';
import StatBlock from './StatBlock.vue';
import VideoInfo from './VideoInfo.vue';
import ChannelHistory from './ChannelHistory.vue';
import { ref, watch } from 'vue';

const props = defineProps({
  item: { type: Object, required: true },
  scale: { type: [Number, String], default: 0 },
  period: { type: String, default: null },
});

const showDetails = ref(false);
const copied = ref(false);
const copiedLabel = ref('ID скопирован');
const logoSrc = ref(localLogo(props.item));

function localLogo(ch) {
  return ch?.custom_url ? `channel_logo/${ch.custom_url}.jpg` : '';
}

function onLogoError() {
  const yt = props.item?.thumbnail_url;
  if (yt && logoSrc.value !== yt) {
    logoSrc.value = yt;
  }
}

watch(
  () => props.item.channel_id,
  () => {
    logoSrc.value = localLogo(props.item);
  }
);

function mapVideo(v) {
  return {
    video_id: v.video_id,
    title: v.title,
    is_short: v.is_short ? 1 : 0,
    is_clickbait: v.is_clickbait ? 1 : 0,
    clickbait_comment: v.clickbait_comment,
    video_url: v.video_url,
    thumbnail_url: v.thumbnail_url,
    published_at: v.published_at,
    stat: {
      duration: v.duration,
      score: v.score,
      view_count: v.period_view_count,
      like_count: v.period_like_count,
      comment_count: v.period_comment_count,
    },
  };
}

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
  if (props.item.top_videos != null || props.item.videos_loading) return;
  if (!props.period) return;

  props.item.videos_loading = true;
  props.item.videos_error = null;
  try {
    const { data: res } = await axios.get('videos', {
      params: {
        channel_id: props.item.channel_id,
        period: props.period,
        limit: 10,
      },
    });
    props.item.top_videos = (res.videos || []).map(mapVideo);
  } catch (err) {
    props.item.videos_error = err.message || String(err);
    props.item.top_videos = [];
  } finally {
    props.item.videos_loading = false;
  }
}

async function loadHistory() {
  if (props.item.history != null || props.item.history_loading) return;

  props.item.history_loading = true;
  props.item.history_error = null;
  try {
    const { data: res } = await axios.get('channel', {
      params: {
        channel_id: props.item.channel_id,
        months: 12,
      },
    });
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

  await loadVideos();
  await loadHistory();
}

watch(
  () => props.period,
  () => {
    props.item.top_videos = null;
    props.item.videos_error = null;
    // history is multi-period — keep cache
    if (showDetails.value) {
      loadVideos().then(() => loadHistory());
    }
  }
);
</script>

<template>
  <div>
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
          <div class="flex items-center" :title="item.description">
            <div :class="showDetails ? 'rotate-90 ' : 'rotate-0'" class="bg-gray-50 p-1 select-none">
              <img
                @click="toggleDetails"
                class="cursor-pointer mr-1"
                src="/img/arrowPeekRight.svg"
                alt="Показать топ видео канала"
              />
            </div>
            <a
              target="_blank"
              class="hover:underline text-base md:text-lg font-semibold ml-1"
              :href="'https://www.youtube.com/' + item.custom_url"
            >
              {{ item.channel_title }}
            </a>
          </div>
        </div>

        <div class="min-w-fit">
          <stat-block class="text-sm" :stat="item.stat" />
        </div>
      </div>
    </div>

    <div
      v-if="showDetails"
      class="text-xs w-auto p-2 ml-5 md:ml-32 -mt-4 shadow-lg bg-gray-50 rounded-lg text-black"
    >
      <div v-if="item.videos_loading" class="flex items-center gap-2 p-3 text-gray-500">
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
          v-for="(video, index) in item.top_videos"
          :key="video.video_id"
        >
          <video-info :video="video" :index="index" />
        </div>
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
