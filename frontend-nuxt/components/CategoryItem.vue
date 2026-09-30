<script setup lang="ts">
/**
 * Category header bar — same layout language as ChannelItem,
 * without rank column; stays within page width on narrow screens.
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
  <div class="relative w-full min-w-0">
    <div
      class="flex items-start bg-white text-black shadow-md w-full min-w-0 my-2 rounded-lg p-1 gap-1 md:gap-4"
    >
      <div class="flex justify-between flex-col md:flex-row w-full min-w-0 gap-2">
        <div class="min-w-0 flex-1">
          <div class="flex items-center relative min-w-0" :title="description || undefined">
            <div class="relative shrink-0">
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
            <span class="text-xl md:text-2xl font-bold ml-1 leading-tight break-words">
              {{ title }}
            </span>
          </div>
        </div>

        <div class="min-w-0 w-full md:w-auto md:max-w-full overflow-x-auto">
          <StatBlock wide class="text-sm" :stat="stat" />
        </div>
      </div>
    </div>

    <div
      v-if="expanded"
      class="text-xs w-full min-w-0 p-2 -mt-4 shadow-lg bg-gray-50 rounded-lg text-black space-y-3"
    >
      <slot />
    </div>
  </div>
</template>
