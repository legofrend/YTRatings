<script setup lang="ts">
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
}>()

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
    <div class="font-medium text-sm mb-1">Ключевые смыслы месяца</div>
    <div
      v-for="row in rows"
      :key="row.key"
      class="flex items-start gap-1 ml-1 my-1.5"
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
        class="min-w-0 flex-1 select-text flex flex-wrap gap-x-3 gap-y-5"
        style="
          background-image: repeating-linear-gradient(
            to bottom,
            transparent 0,
            transparent 19px,
            rgb(209 213 219) 19px,
            rgb(209 213 219) 20px,
            transparent 20px,
            transparent 60px
          );
        "
      >
        <!-- row = h-5 word + mt-1 + leading-4 freq + gap-y-5 ≈ 60px; line at 20px -->
        <div
          v-for="w in row.items"
          :key="row.key + '-' + w.lexeme"
          class="flex flex-col items-center"
          :title="tip(w)"
        >
          <span class="leading-5 h-5">{{ w.word }}</span>
          <span class="text-[10px] text-gray-500 leading-4 mt-1">{{ w.freq }}</span>
        </div>
      </div>
      <span v-else class="text-gray-400 leading-5">—</span>
    </div>
  </div>
</template>
