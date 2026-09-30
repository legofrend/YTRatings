<script setup lang="ts">
import { computed, ref, watch } from 'vue'

export type WordstatItem = {
  lexeme: string
  word: string
  freq: number
  type: number | null
}

export type WordstatReport = {
  leaving: WordstatItem[]
  core: WordstatItem[]
  ['new']: WordstatItem[]
}

const props = defineProps<{
  report: WordstatReport
  /** For /wordstat_img/{id}_{YYYY-MM}.svg hover / side preview. */
  categoryId?: number | null
  period?: string | null
}>()

const showCloud = ref(false)
const cloudOk = ref(true)
const cloudExpanded = ref(false)

const cloudSrc = computed(() => {
  const id = props.categoryId
  const p = props.period
  if (id == null || !p) return null
  // period is YYYY-MM-DD from API → YYYY-MM for filename
  const ym = String(p).slice(0, 7)
  if (!/^\d{4}-\d{2}$/.test(ym)) return null
  return `/wordstat_img/${id}_${ym}.svg`
})

function onCloudError() {
  cloudOk.value = false
  showCloud.value = false
  cloudExpanded.value = false
}

watch(cloudSrc, () => {
  cloudOk.value = true
})

function byFreqDesc(list: WordstatItem[]) {
  return [...list].sort((a, b) => b.freq - a.freq || a.word.localeCompare(b.word, 'ru'))
}

const rows = computed(() => [
  {
    key: 'new',
    items: byFreqDesc(props.report.new),
    mark: 'up' as const,
  },
  {
    key: 'core',
    items: byFreqDesc(props.report.core),
    mark: 'core' as const,
  },
  {
    key: 'leaving',
    items: byFreqDesc(props.report.leaving),
    mark: 'down' as const,
  },
])

function tip(w: WordstatItem) {
  return `${w.lexeme} · ${w.freq}`
}
</script>

<template>
  <div class="wordstat text-xs">
    <div class="flex items-stretch gap-3">
      <div class="min-w-0 flex-1">
        <div
          class="font-medium text-sm mb-1 relative inline-block"
          :class="cloudSrc && cloudOk ? 'cursor-help hover:underline md:cursor-default md:hover:no-underline' : ''"
          @mouseenter="cloudSrc && cloudOk && (showCloud = true)"
          @mouseleave="showCloud = false"
        >
          Ключевые смыслы месяца
          <!-- hover preview when side image is hidden (< md) -->
          <img
            v-if="showCloud && cloudSrc && cloudOk"
            :src="cloudSrc"
            class="absolute z-20 left-0 top-full mt-1 w-[min(28rem,90vw)] max-w-[90vw] rounded shadow-lg border border-gray-200 bg-white pointer-events-none md:hidden"
            alt="Облако слов"
            @error="onCloudError"
          />
        </div>

        <div
          v-for="row in rows"
          :key="row.key"
          class="flex items-start gap-1 ml-1 border-b border-gray-300 pb-0.5 mb-1 last:mb-0"
        >
          <span
            class="shrink-0 w-4 h-5 flex items-center justify-center"
            :title="row.mark === 'up' ? 'Новые' : row.mark === 'down' ? 'Ушли' : 'Ядро'"
          >
            <span v-if="row.mark === 'up'" class="text-green-500 leading-none">▲</span>
            <span v-else-if="row.mark === 'down'" class="text-red-500 leading-none">▼</span>
            <span
              v-else
              class="w-2.5 h-2.5 box-border border border-current opacity-40 rounded-sm"
            />
          </span>
          <div
            v-if="row.items.length"
            class="min-w-0 flex-1 select-text flex flex-wrap gap-x-2.5 gap-y-0.5"
          >
            <span
              v-for="w in row.items"
              :key="row.key + '-' + w.lexeme"
              class="leading-5"
              :title="tip(w)"
            >{{ w.word }}</span>
          </div>
          <span v-else class="text-gray-400 leading-5">—</span>
        </div>
      </div>

      <div
        v-if="cloudSrc && cloudOk"
        class="hidden md:block shrink-0 self-stretch transition-[width] duration-200 ease-out"
        :class="cloudExpanded ? 'w-1/2' : 'w-[28%]'"
        @mouseenter="cloudExpanded = true"
        @mouseleave="cloudExpanded = false"
      >
        <img
          :src="cloudSrc"
          class="w-full h-full object-contain rounded border border-gray-200 bg-white cursor-zoom-in"
          alt="Облако слов"
          @error="onCloudError"
        />
      </div>
    </div>
  </div>
</template>
