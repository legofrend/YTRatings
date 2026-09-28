<script setup lang="ts">
/**
 * Category header bar — same layout language as ChannelItem,
 * shifted left for tree hierarchy vs channel rows.
 */
import StatBlock from './StatBlock.vue'

defineProps<{
  title: string
  description?: string | null
  stat: Record<string, any>
  expanded: boolean
  showHelp?: boolean
}>()

defineEmits<{
  toggle: []
}>()
</script>

<template>
  <div class="relative">
    <div
      class="flex items-center bg-white text-black shadow-md w-full min-w-fit my-2 rounded-lg p-1 space-x-1 md:space-x-4"
    >
      <!-- spacer ≈ channel rank column (no place in category sum) -->
      <div class="flex flex-col items-center w-5 md:w-8 shrink-0" aria-hidden="true" />

      <!-- spacer ≈ channel logo -->
      <div
        class="h-10 w-10 md:h-16 md:w-16 shrink-0 rounded-sm border border-dashed border-gray-300 bg-gray-50"
        aria-hidden="true"
      />

      <div class="flex justify-between flex-col md:flex-row w-full min-w-0">
        <div>
          <div class="flex items-center relative" :title="description || undefined">
            <div class="relative">
              <div
                :class="expanded ? 'rotate-90' : 'rotate-0'"
                class="bg-gray-50 p-1 select-none"
              >
                <img
                  class="cursor-pointer mr-1"
                  src="/img/arrowPeekRight.svg"
                  alt="Детали категории"
                  title="Ключевые смыслы, топ видео и динамика"
                  @click="$emit('toggle')"
                />
              </div>
              <div
                v-if="showHelp"
                class="absolute left-0 top-full mt-2 z-50 w-52 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
                @click.stop
              >
                Нажмите, чтобы посмотреть смыслы месяца, топ видео и динамику категории
              </div>
            </div>
            <span class="text-base md:text-lg font-semibold ml-1">
              {{ title }}
            </span>
          </div>
        </div>

        <div class="min-w-fit">
          <StatBlock class="text-sm" :stat="stat" />
        </div>
      </div>
    </div>

    <div
      v-if="expanded"
      class="text-xs w-auto p-2 ml-5 md:ml-32 -mt-4 shadow-lg bg-gray-50 rounded-lg text-black space-y-3"
    >
      <slot />
    </div>
  </div>
</template>
