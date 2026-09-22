<script setup lang="ts">
import type { Category } from '~/utils/report'

const props = withDefaults(
  defineProps<{
    /** From Nuxt error.vue; omit on /404 page. */
    statusCode?: number
    statusMessage?: string
  }>(),
  {
    statusCode: 404,
    statusMessage: 'Страница не найдена',
  }
)

const { categories: fetchCategories } = useYtrApi()

const { data: categories } = await useAsyncData('not-found-categories', async () => {
  try {
    const cats = (await fetchCategories()) as Category[]
    return cats.filter((c) => c.id !== 0 && c.sys_name)
  } catch {
    return [] as Category[]
  }
})

const code = computed(() => props.statusCode || 404)
const message = computed(
  () => props.statusMessage || (code.value === 404 ? 'Страница не найдена' : 'Ошибка')
)

async function goCategory(sysName: string) {
  if (!sysName) return
  clearError()
  await navigateTo(`/${sysName}`)
}

async function goHome() {
  const first = categories.value?.[0]?.sys_name
  clearError()
  await navigateTo(first ? `/${first}` : '/')
}
</script>

<template>
  <div class="mx-auto px-2 max-w-screen-lg min-h-[60vh]">
    <h1 class="flex flex-wrap items-center justify-center gap-2 text-xl md:text-4xl my-3">
      Рейтинг
      <img
        class="h-6 md:h-8"
        src="/img/youtube_logo_black.svg"
        alt="ютуб YouTube"
      />
      каналов в России и в мире
    </h1>
    <p class="text-center text-xs md:text-sm text-white/70 max-w-2xl mx-auto mb-3 px-2">
      Топ рейтинг самых популярных ютуб-каналов в России и в мире.
    </p>

    <div
      class="relative flex flex-col md:flex-row justify-center items-center shadow select-none gap-1 md:gap-5 py-1"
    >
      <select
        v-if="categories?.length"
        class="pl-1 text-black text-base cursor-pointer rounded"
        name="category"
        @change="goCategory(($event.target as HTMLSelectElement).value)"
      >
        <option disabled selected value="">— выберите категорию —</option>
        <option
          v-for="category in categories"
          :key="category.id"
          class="text-left"
          :value="category.sys_name!"
        >
          {{ category.name }}
        </option>
      </select>
      <button
        type="button"
        class="text-sm underline opacity-80 hover:opacity-100"
        @click="goHome"
      >
        на главную
      </button>
    </div>

    <!-- No-JS / crawlers: real links baked into SSG HTML -->
    <nav
      v-if="categories?.length"
      class="flex flex-wrap justify-center gap-x-3 gap-y-1 text-sm text-white/70 mt-4 px-2"
      aria-label="Категории"
    >
      <NuxtLink
        v-for="category in categories"
        :key="category.id"
        :to="`/${category.sys_name}`"
        class="hover:text-white hover:underline"
      >
        {{ category.name }}
      </NuxtLink>
    </nav>

    <p class="text-center text-base md:text-lg py-10 px-4">
      <span class="opacity-60">{{ code }}</span>
      · {{ message }}
    </p>
  </div>
</template>
