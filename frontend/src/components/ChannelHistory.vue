<script setup>
import { computed } from 'vue';

const props = defineProps({
  points: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const W = 640;
const H = 220;
const PAD = { t: 28, r: 48, b: 28, l: 48 };
const RANK_SIZE = 18;

function shortPeriod(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  return `${months[d.getMonth()]}'${String(d.getFullYear()).slice(2)}`;
}

function fmtNum(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return (Math.round(n / 1e5) / 10).toFixed(1) + 'M';
  if (Math.abs(n) >= 1e3) return Math.round(n / 1e3) + 'K';
  return String(Math.round(n));
}

function scaleRange(vals) {
  const nums = vals.filter((v) => v != null && !Number.isNaN(Number(v))).map(Number);
  if (!nums.length) return { min: 0, max: 1 };
  const max = Math.max(...nums, 0);
  // always from 0 — иначе мелкие колебания выглядят огромными
  return { min: 0, max: max === 0 ? 1 : max };
}

const chart = computed(() => {
  const raw = props.points || [];
  if (!raw.length) return null;

  const rows = raw.map((p) => ({
    label: shortPeriod(p.report_period),
    score: p.pv_score,
    subs: p.subscriber_count,
    rank: p.rank,
  }));

  const scoreScale = scaleRange(rows.map((r) => r.score));
  const subsScale = scaleRange(rows.map((r) => r.subs));

  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  const n = rows.length;
  const slot = innerW / n;
  const barW = Math.min(28, slot * 0.55);

  const yScore = (v) => {
    if (v == null) return null;
    const t = (Number(v) - scoreScale.min) / (scoreScale.max - scoreScale.min);
    return PAD.t + (1 - t) * innerH;
  };
  const ySubs = (v) => {
    if (v == null) return null;
    const t = (Number(v) - subsScale.min) / (subsScale.max - subsScale.min);
    return PAD.t + (1 - t) * innerH;
  };
  const baseline = PAD.t + innerH;

  const bars = rows.map((r, i) => {
    const cx = PAD.l + slot * i + slot / 2;
    const yTop = yScore(r.score);
    const h = yTop == null ? 0 : Math.max(0, baseline - yTop);
    return {
      ...r,
      cx,
      barX: cx - barW / 2,
      barY: yTop ?? baseline,
      barH: h,
      barW,
      subsY: ySubs(r.subs),
      rankY: (yTop ?? baseline) - RANK_SIZE - 4,
    };
  });

  const subsLine = bars
    .filter((b) => b.subsY != null)
    .map((b) => `${b.cx},${b.subsY}`)
    .join(' ');

  return {
    bars,
    subsLine,
    scoreScale,
    subsScale,
    baseline,
    innerH,
  };
});
</script>

<template>
  <div class="mt-3 pt-2 border-t border-gray-200">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
      <div class="text-xs font-semibold text-gray-800">Динамика (12 мес.)</div>
      <div class="flex flex-wrap gap-3 text-[10px] text-gray-600">
        <span class="inline-flex items-center gap-1">
          <span class="inline-block w-2.5 h-2.5 bg-blue-400/80 rounded-sm" /> индекс
        </span>
        <span class="inline-flex items-center gap-1">
          <span class="inline-block w-3 h-0.5 bg-purple-600" /> подписчики
        </span>
        <span class="inline-flex items-center gap-1">
          <span
            class="inline-flex justify-center items-center bg-green-500 text-white font-bold w-3.5 h-3.5 rounded-sm text-[8px]"
          >1</span>
          место
        </span>
      </div>
    </div>

    <div v-if="loading" class="flex items-center gap-2 p-3 text-gray-500">
      <span
        class="inline-block h-4 w-4 rounded-full border-2 border-gray-300 border-t-blue-500 animate-spin"
      />
      Загрузка динамики…
    </div>
    <div v-else-if="error" class="p-2 text-red-600">{{ error }}</div>
    <div v-else-if="!chart" class="text-xs text-gray-400 py-4">Нет данных</div>
    <svg
      v-else
      :viewBox="`0 0 ${W} ${H}`"
      class="w-full max-h-64 bg-white rounded border border-gray-200"
    >
      <!-- grid -->
      <line
        :x1="PAD.l"
        :x2="W - PAD.r"
        :y1="chart.baseline"
        :y2="chart.baseline"
        stroke="#e5e7eb"
        stroke-width="1"
      />

      <!-- left axis: score -->
      <text :x="4" :y="PAD.t + 4" class="fill-blue-600" font-size="9">индекс</text>
      <text :x="4" :y="PAD.t + 14" class="fill-blue-500" font-size="8">
        {{ fmtNum(chart.scoreScale.max) }}
      </text>
      <text :x="4" :y="chart.baseline" class="fill-blue-500" font-size="8">
        {{ fmtNum(chart.scoreScale.min) }}
      </text>

      <!-- right axis: subs -->
      <text
        :x="W - 4"
        :y="PAD.t + 4"
        text-anchor="end"
        class="fill-purple-700"
        font-size="9"
      >подписчики</text>
      <text
        :x="W - 4"
        :y="PAD.t + 14"
        text-anchor="end"
        class="fill-purple-500"
        font-size="8"
      >
        {{ fmtNum(chart.subsScale.max) }}
      </text>
      <text
        :x="W - 4"
        :y="chart.baseline"
        text-anchor="end"
        class="fill-purple-500"
        font-size="8"
      >
        {{ fmtNum(chart.subsScale.min) }}
      </text>

      <!-- bars: score (pv_score) -->
      <rect
        v-for="(b, i) in chart.bars"
        :key="'bar' + i"
        :x="b.barX"
        :y="b.barY"
        :width="b.barW"
        :height="b.barH"
        fill="#60a5fa"
        opacity="0.85"
        rx="2"
      >
        <title>{{ b.label }}: индекс {{ fmtNum(b.score) }}</title>
      </rect>

      <!-- line: subscribers -->
      <polyline
        v-if="chart.subsLine"
        fill="none"
        stroke="#9333ea"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
        :points="chart.subsLine"
      />
      <circle
        v-for="(b, i) in chart.bars"
        :key="'sub' + i"
        v-show="b.subsY != null"
        :cx="b.cx"
        :cy="b.subsY"
        r="3"
        fill="#9333ea"
      >
        <title>{{ b.label }}: {{ fmtNum(b.subs) }} подписчиков</title>
      </circle>

      <!-- rank markers above bars (no line) -->
      <g v-for="(b, i) in chart.bars" :key="'rank' + i" v-show="b.rank != null">
        <rect
          :x="b.cx - RANK_SIZE / 2"
          :y="b.rankY"
          :width="RANK_SIZE"
          :height="RANK_SIZE"
          rx="3"
          fill="#22c55e"
        />
        <text
          :x="b.cx"
          :y="b.rankY + RANK_SIZE / 2 + 3.5"
          text-anchor="middle"
          fill="white"
          font-size="10"
          font-weight="700"
        >
          {{ b.rank }}
        </text>
        <title>{{ b.label }}: место {{ b.rank }}</title>
      </g>

      <!-- x labels -->
      <text
        v-for="(b, i) in chart.bars"
        :key="'lbl' + i"
        :x="b.cx"
        :y="H - 8"
        text-anchor="middle"
        class="fill-gray-500"
        font-size="9"
      >
        {{ b.label }}
      </text>
    </svg>
  </div>
</template>
