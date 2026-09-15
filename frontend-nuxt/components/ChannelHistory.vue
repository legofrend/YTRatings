<script setup>
import { computed } from 'vue';

const props = defineProps({
  points: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  /** Category aggregate: bars only + MoM % label above score (no subs / rank / line). */
  scoreOnly: { type: Boolean, default: false },
  title: { type: String, default: 'Динамика (12 мес.)' },
});

const W = 720;
const H = 236;
const PAD = { t: 40, r: 12, b: 28, l: 12 };
const RANK_SIZE = 18;
/** Visual height of subs 0→max = 1.2 × height of score 0→max (same baseline). */
const SUBS_TO_SCORE_AXIS = 1.2;

/** Stack segments bottom → top. Shorts = muted blues (same family). */
const SEGMENTS = [
  { key: 'newLong', label: 'новые видео', color: '#1d4ed8' },
  { key: 'oldLong', label: 'старые видео', color: '#93c5fd' },
  { key: 'newShort', label: 'новые shorts ÷10', color: '#60a5fa' },
  { key: 'oldShort', label: 'старые shorts ÷10', color: '#bfdbfe' },
];

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

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return null;
  const n = Number(v);
  const sign = n > 0 ? '+' : '';
  return sign + Math.round(n) + '%';
}

function scoreTooltip(label, p, momPct) {
  const newLong = Number(p.pv_view_new_long) || 0;
  const oldLong = Number(p.pv_view_old_long) || 0;
  const newShort = Number(p.pv_view_new_short) || 0;
  const oldShort = Number(p.pv_view_old_short) || 0;
  const score =
    Number(p.pv_score) ||
    newLong + oldLong + newShort / 10 + oldShort / 10;
  let tip =
    `${label}\n` +
    `Индекс (${fmtNum(score)}) = ${fmtNum(newLong)} + ${fmtNum(oldLong)} + ${fmtNum(newShort)}/10 + ${fmtNum(oldShort)}/10`;
  const pct = fmtPct(momPct);
  if (pct) tip += `\nΔ к пред. мес.: ${pct}`;
  return tip;
}

function fmtSubsDelta(v) {
  if (v == null || Number(v) === 0) return null;
  const m = Number(v) / 1e6;
  const sign = m > 0 ? '+' : '';
  return sign + m.toFixed(2).replace('.', ',');
}

function scaleRange(vals) {
  const nums = vals.filter((v) => v != null && !Number.isNaN(Number(v))).map(Number);
  if (!nums.length) return { min: 0, max: 1 };
  const max = Math.max(...nums, 0);
  return { min: 0, max: max === 0 ? 1 : max };
}

function scoreParts(p) {
  const newLong = Math.max(0, Number(p.pv_view_new_long) || 0);
  const oldLong = Math.max(0, Number(p.pv_view_old_long) || 0);
  const newShort = Math.max(0, (Number(p.pv_view_new_short) || 0) / 10);
  const oldShort = Math.max(0, (Number(p.pv_view_old_short) || 0) / 10);
  const parts = { newLong, oldLong, newShort, oldShort };
  const sum = newLong + oldLong + newShort + oldShort;
  if (sum <= 0 && p.pv_score) {
    return { newLong: Number(p.pv_score) || 0, oldLong: 0, newShort: 0, oldShort: 0 };
  }
  return parts;
}

function rankFill(rankChange) {
  if (rankChange == null) return '#9ca3af';
  const ui = -Number(rankChange);
  if (ui > 0) return '#22c55e';
  if (ui < 0) return '#ef4444';
  return '#9ca3af';
}

const chart = computed(() => {
  const raw = props.points || [];
  if (!raw.length) return null;

  const rows = raw.map((p, i, arr) => {
    const parts = scoreParts(p);
    const score =
      parts.newLong + parts.oldLong + parts.newShort + parts.oldShort ||
      Number(p.pv_score) ||
      0;
    const label = shortPeriod(p.report_period);
    let scoreMomPct = null;
    if (i > 0) {
      const prevParts = scoreParts(arr[i - 1]);
      const prev =
        prevParts.newLong +
          prevParts.oldLong +
          prevParts.newShort +
          prevParts.oldShort ||
        Number(arr[i - 1].pv_score) ||
        0;
      if (prev > 0) scoreMomPct = ((score - prev) / prev) * 100;
    }
    return {
      label,
      score,
      scoreMomPct,
      parts,
      tooltip: scoreTooltip(label, p, scoreMomPct),
      subs: p.subscriber_count,
      subsDelta: p.pc_subscriber,
      rank: p.rank,
      rankChange: p.rank_change,
    };
  });

  const scoreScale = scaleRange(rows.map((r) => r.score));
  const subsScale = scaleRange(rows.map((r) => r.subs));

  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  const n = rows.length;
  const slot = innerW / n;
  const barW = Math.min(props.scoreOnly ? 22 : 28, slot * 0.55);
  const baseline = PAD.t + innerH;

  // score-only: full chart height for bars; else score band = innerH/1.2 under subs
  const scoreAxisH = props.scoreOnly ? innerH : innerH / SUBS_TO_SCORE_AXIS;
  const subsAxisH = innerH;

  const ySubs = (v) => {
    if (props.scoreOnly || v == null) return null;
    const t = (Number(v) - subsScale.min) / (subsScale.max - subsScale.min);
    return baseline - t * subsAxisH;
  };

  const px = (val) =>
    scoreScale.max > 0 ? (Number(val) / scoreScale.max) * scoreAxisH : 0;

  const last = n - 1;
  const bars = rows.map((r, i) => {
    const cx = PAD.l + slot * i + slot / 2;
    let yCursor = baseline;
    const segs = [];
    for (const seg of SEGMENTS) {
      const val = r.parts[seg.key] || 0;
      if (val <= 0) continue;
      const h = px(val);
      const y = yCursor - h;
      segs.push({
        key: seg.key,
        color: seg.color,
        label: seg.label,
        x: cx - barW / 2,
        y,
        w: barW,
        h: Math.max(0, h),
        val,
      });
      yCursor = y;
    }

    const isEdge = i === 0 || i === last;
    let subsLabel = null;
    let subsLabelClass = 'fill-purple-700';
    if (!props.scoreOnly) {
      if (isEdge && r.subs != null) {
        subsLabel = fmtNum(r.subs);
        subsLabelClass = 'fill-purple-700';
      } else {
        const d = fmtSubsDelta(r.subsDelta);
        if (d) {
          subsLabel = d;
          subsLabelClass = r.subsDelta > 0 ? 'fill-green-600' : 'fill-red-600';
        }
      }
    }

    const pctLabel = props.scoreOnly ? fmtPct(r.scoreMomPct) : null;
    let pctLabelClass = 'fill-purple-700';
    if (r.scoreMomPct != null) {
      if (r.scoreMomPct > 0) pctLabelClass = 'fill-green-600';
      else if (r.scoreMomPct < 0) pctLabelClass = 'fill-red-600';
    }

    // Score above bar; MoM % above score label.
    const scoreLabelY = Math.max(18, yCursor - 4);
    const pctLabelY = pctLabel ? Math.max(10, scoreLabelY - 11) : null;

    return {
      ...r,
      cx,
      barX: cx - barW / 2,
      barW,
      segs,
      barTop: yCursor,
      scoreLabelY,
      scoreLabel: fmtNum(r.score),
      pctLabelY,
      pctLabel,
      pctLabelClass,
      subsY: ySubs(r.subs),
      rankY: baseline - RANK_SIZE,
      rankFill: rankFill(r.rankChange),
      showRank: !props.scoreOnly && r.rank != null,
      subsLabel,
      subsLabelClass,
    };
  });

  const subsLine = props.scoreOnly
    ? ''
    : bars
        .filter((b) => b.subsY != null)
        .map((b) => `${b.cx},${b.subsY}`)
        .join(' ');

  return {
    bars,
    subsLine,
    baseline,
    segments: SEGMENTS,
    scoreOnly: props.scoreOnly,
  };
});
</script>

<template>
  <div class="mt-3 pt-2 border-t border-gray-200">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
      <div class="text-xs font-semibold text-gray-800">{{ title }}</div>
      <div class="flex flex-wrap gap-2 text-[10px] text-gray-600">
        <span
          v-for="s in (chart?.segments || SEGMENTS)"
          :key="s.key"
          class="inline-flex items-center gap-1"
        >
          <span class="inline-block w-2.5 h-2.5 rounded-sm" :style="{ background: s.color }" />
          {{ s.label }}
        </span>
        <template v-if="!scoreOnly">
          <span class="inline-flex items-center gap-1">
            <span class="inline-block w-3 h-0.5 bg-purple-600" /> подписчики
          </span>
          <span class="inline-flex items-center gap-1">
            <span
              class="inline-flex justify-center items-center bg-gray-400 text-white font-bold w-3.5 h-3.5 rounded-sm text-[8px]"
            >1</span>
            место (зелёный↑ / красный↓)
          </span>
        </template>
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
      <line
        :x1="PAD.l"
        :x2="W - PAD.r"
        :y1="chart.baseline"
        :y2="chart.baseline"
        stroke="#e5e7eb"
        stroke-width="1"
      />

      <!-- stacked score bars -->
      <g v-for="(b, i) in chart.bars" :key="'stack' + i">
        <title>{{ b.tooltip }}</title>
        <rect
          v-for="(seg, si) in b.segs"
          :key="si"
          :x="seg.x"
          :y="seg.y"
          :width="seg.w"
          :height="seg.h"
          :fill="seg.color"
          opacity="0.95"
        />
        <rect
          :x="b.barX"
          :y="b.barTop"
          :width="b.barW"
          :height="Math.max(0, chart.baseline - b.barTop)"
          fill="transparent"
        >
          <title>{{ b.tooltip }}</title>
        </rect>
        <text
          v-if="b.pctLabel"
          :x="b.cx"
          :y="b.pctLabelY"
          text-anchor="middle"
          :class="b.pctLabelClass"
          font-size="7"
          font-weight="600"
        >
          {{ b.pctLabel }}
        </text>
        <text
          :x="b.cx"
          :y="b.scoreLabelY"
          text-anchor="middle"
          class="fill-blue-800"
          font-size="8"
          font-weight="600"
        >
          {{ b.scoreLabel }}
        </text>
      </g>

      <!-- channel: subscribers + rank -->
      <template v-if="!scoreOnly">
        <polyline
          v-if="chart.subsLine"
          fill="none"
          stroke="#9333ea"
          stroke-width="2"
          stroke-linejoin="round"
          stroke-linecap="round"
          :points="chart.subsLine"
        />
        <g v-for="(b, i) in chart.bars" :key="'sub' + i" v-show="b.subsY != null">
          <circle :cx="b.cx" :cy="b.subsY" r="3" fill="#9333ea">
            <title>{{ b.label }}: {{ fmtNum(b.subs) }} подписчиков</title>
          </circle>
          <text
            v-if="b.subsLabel"
            :x="b.cx"
            :y="b.subsY - 6"
            text-anchor="middle"
            :class="b.subsLabelClass"
            font-size="8"
            font-weight="600"
          >
            {{ b.subsLabel }}
          </text>
        </g>

        <g v-for="(b, i) in chart.bars" :key="'rank' + i" v-show="b.showRank">
          <rect
            :x="b.cx - RANK_SIZE / 2"
            :y="b.rankY"
            :width="RANK_SIZE"
            :height="RANK_SIZE"
            rx="3"
            :fill="b.rankFill"
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
      </template>

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
