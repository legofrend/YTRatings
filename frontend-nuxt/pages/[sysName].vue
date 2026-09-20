<script setup lang="ts">
import {
  channelsScale,
  formattedDate,
  mapChannel,
  mapVideo,
  type Category,
} from '~/utils/report'

const route = useRoute()
const config = useRuntimeConfig()
const {
  categories: fetchCategories,
  periods: fetchPeriods,
  channels: fetchChannels,
  categoryDynamics,
  categoryVideos: fetchCategoryVideos,
} = useYtrApi()

const sysName = computed(() => String(route.params.sysName || ''))
const periodQuery = computed(() => {
  const p = route.query.period
  return typeof p === 'string' && p ? p : null
})
const limit = computed(() => {
  const n = Number(route.query.limit)
  if (!Number.isFinite(n) || n <= 0) return 20
  if (n >= 999) return 999 // «все»
  return Math.min(n, 100)
})
/** Cap for API / category aggregate (backend max 100). */
const apiLimit = computed(() => (limit.value >= 999 ? 100 : limit.value))

const selectedSort = ref('rank')
const sortTypes = [
  { id: 'rank', name: 'Место' },
  { id: 'subscriber_count', name: 'Подписчики' },
  { id: 'like_share', name: 'Доля лайков' },
  { id: 'comment_share', name: 'Доля комментариев' },
  { id: 'duration', name: 'Длительность' },
]

/** SSG payload: category + latest period channels (SEO). */
const { data: page, error, pending } = await useAsyncData(
  () => `cat-${sysName.value}`,
  async () => {
    const cats = (await fetchCategories()) as Category[]
    const cat = cats.find((c) => c.sys_name === sysName.value)
    if (!cat) {
      throw createError({ statusCode: 404, statusMessage: 'Категория не найдена' })
    }

    const { periods } = await fetchPeriods(cat.id)
    if (!periods.length) {
      throw createError({ statusCode: 404, statusMessage: 'Нет периодов' })
    }
    const latestPeriod = periods[0]
    const res = await fetchChannels(cat.id, latestPeriod, 100)
    const channels = (res.channels || []).map(mapChannel)

    return {
      categories: cats.filter((c) => c.id !== 0 && c.sys_name),
      category: cat,
      periods,
      latestPeriod,
      period: res.period,
      scale: channelsScale(channels),
      channels,
    }
  },
  {
    watch: [sysName],
    getCachedData(key, nuxtApp) {
      return nuxtApp.payload.data[key] ?? nuxtApp.static.data[key]
    },
  }
)

const isArchive = computed(() => {
  if (!page.value || !periodQuery.value) return false
  return periodQuery.value !== page.value.latestPeriod
})

const activePeriod = computed(
  () => periodQuery.value || page.value?.latestPeriod || null
)

type ArchiveState = {
  period: string
  channels: ReturnType<typeof mapChannel>[]
  scale: number
}
const archive = ref<ArchiveState | null>(null)
const archivePending = ref(false)
const archiveError = ref<string | null>(null)

async function loadArchive(categoryId: number, period: string) {
  archivePending.value = true
  archiveError.value = null
  try {
    const res = await fetchChannels(categoryId, period, 100)
    const channels = (res.channels || []).map(mapChannel)
    archive.value = {
      period: res.period,
      channels,
      scale: channelsScale(channels),
    }
  } catch (err: any) {
    archive.value = null
    archiveError.value = err?.message || String(err)
  } finally {
    archivePending.value = false
  }
}

watch(
  [isArchive, activePeriod, () => page.value?.category.id],
  ([arch, period, catId]) => {
    if (!arch || !period || catId == null) {
      archive.value = null
      archiveError.value = null
      return
    }
    if (!import.meta.client) return
    loadArchive(catId, period)
  },
  { immediate: true }
)

const viewChannels = computed(() =>
  isArchive.value
    ? archive.value?.channels || []
    : page.value?.channels || []
)
const viewScale = computed(() =>
  isArchive.value
    ? archive.value?.scale || 0
    : page.value?.scale || 0
)
const viewPeriod = computed(
  () =>
    (isArchive.value ? archive.value?.period : page.value?.period) ||
    activePeriod.value
)

const chartData = computed(() => ({
  category: page.value?.category || null,
  period: viewPeriod.value,
  scale: viewScale.value,
  data: viewChannels.value,
}))

const pagePending = computed(
  () => (pending.value && !page.value) || (isArchive.value && archivePending.value)
)
const pageError = computed(
  () => error.value?.message || archiveError.value || null
)

const seoKeywords = computed(() => {
  const cat = page.value?.category
  const base = [
    'рейтинг ютуб каналов',
    'рейтинг youtube каналов',
    'топ рейтинг ютуб каналов',
    'рейтинг ютуб каналов в россии',
    'рейтинг ютуб каналов в мире',
    'ютуб каналы рейтинг по подписчикам',
    'рейтинг каналов ютуб по подписчикам в мире',
    'рейтинг самых популярных каналов на ютубе',
    'топ youtube каналов',
  ]
  if (cat?.name) {
    base.unshift(`рейтинг ютуб каналов ${cat.name}`, `топ youtube ${cat.name}`)
  }
  return base.join(', ')
})

useSeoMeta({
  title: () => {
    const cat = page.value?.category
    const p = viewPeriod.value
    if (!cat || !p) {
      return 'Рейтинг ютуб каналов в России и в мире — топ YouTube | YTRatings'
    }
    return (
      `Рейтинг ютуб каналов: ${cat.name} — ${formattedDate(p)}` +
      ` | топ в России и мире`
    )
  },
  description: () => {
    const cat = page.value?.category
    const p = viewPeriod.value
    if (!cat) {
      return (
        'Топ рейтинг ютуб (YouTube) каналов в России и в мире: самые популярные каналы ' +
        'по просмотрам, подписчикам и динамике. Ежемесячное сравнение.'
      )
    }
    const top = viewChannels.value
      .slice(0, 5)
      .map((c) => c.channel_title)
      .filter(Boolean)
    const topStr = top.length ? ` Лидеры: ${top.join(', ')}.` : ''
    const criteria = cat.description ? ` Критерии: ${cat.description}.` : ''
    return (
      `Топ рейтинг ютуб-каналов «${cat.title || cat.name}» за ${formattedDate(p)} ` +
      `в России. Рейтинг самых популярных каналов на ютубе по просмотрам ` +
      `(видео + shorts×0.1), подписчикам и индексу; также рейтинги каналов в мире.` +
      `${criteria}${topStr}`
    ).slice(0, 320)
  },
  ogTitle: () => {
    const cat = page.value?.category
    const p = viewPeriod.value
    return cat && p
      ? `Рейтинг ютуб каналов «${cat.name}» — ${formattedDate(p)}`
      : 'Рейтинг ютуб каналов в России и в мире'
  },
  ogDescription: () => {
    const cat = page.value?.category
    return cat
      ? `Топ самых популярных ютуб-каналов: ${cat.title || cat.name}. ` +
          `Рейтинг в России и в мире — просмотры, подписчики, динамика.`
      : 'Ежемесячный топ рейтинг ютуб каналов в России и в мире.'
  },
  ogType: 'website',
  ogLocale: 'ru_RU',
  twitterCard: 'summary',
  ogUrl: () => {
    const slug = sysName.value
    const q = new URLSearchParams()
    if (periodQuery.value) q.set('period', periodQuery.value)
    if (limit.value !== 20) q.set('limit', String(limit.value))
    const qs = q.toString()
    return `${config.public.siteUrl}/${slug}${qs ? `?${qs}` : ''}`
  },
})

useHead({
  meta: [{ name: 'keywords', content: seoKeywords }],
})

function ratingQuery(opts: { period?: string | null; limit?: number }) {
  const q: Record<string, string> = {}
  const period = opts.period
  const lim = opts.limit ?? limit.value
  const latest = page.value?.latestPeriod
  if (period && period !== latest) q.period = period
  if (lim !== 20) q.limit = String(lim)
  return q
}

async function changeCategory(nextSysName: string) {
  if (!nextSysName || nextSysName === sysName.value) return
  await navigateTo({
    path: `/${nextSysName}`,
    query: ratingQuery({ period: periodQuery.value }),
  })
}

async function changePeriod(period: string) {
  if (!period || period === activePeriod.value) return
  await navigateTo({
    path: `/${sysName.value}`,
    query: ratingQuery({ period }),
  })
}

function shiftPeriod(delta: number) {
  const list = page.value?.periods || []
  const current = activePeriod.value
  const idx = current ? list.indexOf(current) : -1
  if (idx < 0) return
  const next = idx - delta
  if (next < 0 || next >= list.length) return
  changePeriod(list[next])
}

async function changeLimit(n: number) {
  await navigateTo({
    path: `/${sysName.value}`,
    query: ratingQuery({ period: periodQuery.value, limit: n }),
  })
}

const showCategoryHistory = ref(false)
const categoryHistory = ref<Record<string, any>[] | null>(null)
const categoryHistoryLoading = ref(false)
const categoryHistoryError = ref<string | null>(null)
const categoryHistoryKey = ref('')
/** Default 12; left arrow expands to 24. */
const categoryHistoryMonths = ref<12 | 24>(12)

const CATEGORY_VIDEOS_STEP = 5
const CATEGORY_VIDEOS_MAX = 20

const categoryTopVideos = ref<ReturnType<typeof mapVideo>[] | null>(null)
const categoryTopVideosLoading = ref(false)
const categoryTopVideosError = ref<string | null>(null)
const categoryTopVideosKey = ref('')
/** How many category top videos to show (5 → 10 → 15 → 20). Fetch always pulls MAX. */
const categoryTopVideosLimit = ref(CATEGORY_VIDEOS_STEP)

const visibleCategoryTopVideos = computed(() => {
  const list = categoryTopVideos.value || []
  return list.slice(0, categoryTopVideosLimit.value)
})
const canExpandCategoryTopVideos = computed(() => {
  const n = categoryTopVideos.value?.length || 0
  return categoryTopVideosLimit.value < Math.min(CATEGORY_VIDEOS_MAX, n)
})

async function loadCategoryHistory(force = false) {
  const catId = page.value?.category?.id
  if (catId == null) return
  const months = categoryHistoryMonths.value
  const key = `${catId}:${apiLimit.value}:${months}`
  if (!force && categoryHistory.value && categoryHistoryKey.value === key) return

  categoryHistoryLoading.value = true
  categoryHistoryError.value = null
  try {
    const res = await categoryDynamics(catId, apiLimit.value, months)
    categoryHistory.value = res.points || []
    categoryHistoryKey.value = key
  } catch (err: any) {
    categoryHistory.value = null
    categoryHistoryError.value = err?.data?.detail || err?.message || String(err)
  } finally {
    categoryHistoryLoading.value = false
  }
}

async function loadCategoryTopVideos(force = false) {
  const catId = page.value?.category?.id
  const period = viewPeriod.value
  if (catId == null || !period) return
  const key = `${catId}:${period}`
  if (
    !force &&
    categoryTopVideos.value &&
    categoryTopVideosKey.value === key
  ) {
    return
  }

  categoryTopVideosLoading.value = true
  categoryTopVideosError.value = null
  try {
    // one shot: fetch max, UI reveals by STEP
    const res = await fetchCategoryVideos(catId, period, CATEGORY_VIDEOS_MAX)
    categoryTopVideos.value = (res.videos || []).map(mapVideo)
    categoryTopVideosKey.value = key
  } catch (err: any) {
    categoryTopVideos.value = null
    categoryTopVideosError.value = err?.data?.detail || err?.message || String(err)
  } finally {
    categoryTopVideosLoading.value = false
  }
}

function expandCategoryTopVideos() {
  categoryTopVideosLimit.value = Math.min(
    categoryTopVideosLimit.value + CATEGORY_VIDEOS_STEP,
    CATEGORY_VIDEOS_MAX
  )
}

async function toggleCategoryHistory() {
  showCategoryHistory.value = !showCategoryHistory.value
  if (!showCategoryHistory.value) {
    categoryHistoryMonths.value = 12
    categoryTopVideosLimit.value = CATEGORY_VIDEOS_STEP
    return
  }
  await Promise.all([loadCategoryHistory(), loadCategoryTopVideos()])
}

async function toggleCategoryHistoryMonths() {
  categoryHistoryMonths.value = categoryHistoryMonths.value === 12 ? 24 : 12
  await loadCategoryHistory(true)
}

watch(limit, () => {
  if (showCategoryHistory.value) loadCategoryHistory(true)
})

watch(viewPeriod, () => {
  if (!showCategoryHistory.value) return
  categoryTopVideosLimit.value = CATEGORY_VIDEOS_STEP
  loadCategoryTopVideos(true)
})

const showHelp = ref(false)
const topNumbers = [
  { value: 10, name: 'топ 10' },
  { value: 20, name: 'топ 20' },
  { value: 100, name: 'топ 100' },
]

function toggleHelp(e: Event) {
  e.stopPropagation()
  showHelp.value = !showHelp.value
}

function onHelpDocClick() {
  if (showHelp.value) showHelp.value = false
}

onMounted(() => {
  document.addEventListener('click', onHelpDocClick)
})
onUnmounted(() => {
  document.removeEventListener('click', onHelpDocClick)
})

watch(sysName, () => {
  showCategoryHistory.value = false
  categoryHistory.value = null
  categoryHistoryKey.value = ''
  categoryHistoryError.value = null
  categoryHistoryMonths.value = 12
  categoryTopVideos.value = null
  categoryTopVideosKey.value = ''
  categoryTopVideosError.value = null
  categoryTopVideosLimit.value = CATEGORY_VIDEOS_STEP
  showHelp.value = false
})

</script>

<template>
  <div class="mx-auto px-2 max-w-screen-lg">
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
      Топ рейтинг самых популярных ютуб-каналов в России и в мире — по просмотрам,
      подписчикам и динамике. Ежемесячное сравнение YouTube-каналов.
    </p>

    <p v-if="pagePending && !page">Loading...</p>
    <p v-else-if="pageError && !page">{{ pageError }}</p>
    <div v-else-if="page">
      <div
        class="relative flex flex-col md:flex-row justify-center items-center shadow select-none gap-1 md:gap-5 py-1"
      >
        <div class="relative">
          <select
            :value="sysName"
            class="pl-1 text-black text-base cursor-pointer rounded"
            name="category"
            @change="changeCategory(($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="category in page.categories"
              :key="category.id"
              class="text-left"
              :value="category.sys_name!"
            >
              {{ category.name }}
            </option>
          </select>
          <div
            v-if="showHelp"
            class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-44 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
            @click.stop
          >
            Выберите категорию каналов
          </div>
        </div>

        <select
          :value="limit"
          name="topChannels"
          class="text-black text-base cursor-pointer rounded"
          @change="changeLimit(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="n in topNumbers" :key="n.value" :value="n.value">
            {{ n.name }}
          </option>
        </select>

        <div class="relative flex justify-center items-center select-none gap-1">
          <img
            src="/img/arrowLeftWhite.svg"
            class="h-4 mx-1 cursor-pointer"
            alt=""
            @click="shiftPeriod(-1)"
          />
          <select
            :value="activePeriod || ''"
            class="text-black text-base cursor-pointer rounded"
            name="period"
            @change="changePeriod(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="p in page.periods" :key="p" :value="p">
              {{ formattedDate(p) }}
            </option>
          </select>
          <img
            src="/img/arrowLeftWhite.svg"
            class="h-4 mx-1 cursor-pointer rotate-180"
            alt=""
            @click="shiftPeriod(1)"
          />
          <div
            v-if="showHelp"
            class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-36 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
            @click.stop
          >
            Выберите месяц
          </div>
        </div>

        <div class="relative flex flex-row items-center gap-1">
          <div class="bg-white rounded-lg h-5 w-7 items-center flex justify-center">
            <img src="/img/sortBtn.svg" class="h-4" alt="" />
          </div>
          <select v-model="selectedSort" name="sort" class="text-black cursor-pointer rounded">
            <option
              v-for="sort in sortTypes"
              :key="sort.id"
              class="text-left"
              :value="sort.id"
            >
              {{ sort.name }}
            </option>
          </select>
          <div
            v-if="showHelp"
            class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-56 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
            @click.stop
          >
            Способ сортировки каналов: число просмотров, подписчиков, доля лайков,
            доля комментариев, длительность
          </div>
        </div>

        <div class="relative">
          <button
            type="button"
            class="h-7 w-7 rounded-full border border-white/60 text-white text-sm leading-none hover:bg-white/10"
            title="Справка"
            aria-label="Справка"
            @click="toggleHelp"
          >
            ℹ️
          </button>
          <div
            v-if="showHelp"
            class="absolute right-0 top-full mt-2 z-50 w-72 max-w-[min(18rem,90vw)] rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
            @click.stop
          >
            <div class="font-semibold mb-1">Методика</div>
            Рейтинг на основе суммы просмотров на канале по видео и клипам двух
            последних месяцев. Клипы (shorts) учитываются с коэффициентом 1/10.
            <p v-if="page.category?.description" class="mt-1">
              Критерии выбора каналов: {{ page.category.description }}
            </p>
          </div>
        </div>
      </div>

      <h2 class="flex items-center justify-center gap-2 text-xl md:text-3xl my-3">
        <div class="relative">
          <div
            :class="showCategoryHistory ? 'rotate-90' : 'rotate-0'"
            class="bg-gray-50 p-1 select-none shrink-0"
          >
            <img
              class="cursor-pointer"
              src="/img/arrowPeekRight.svg"
              alt="Динамика категории"
              title="Сумма индекса топ-N каналов за 12 мес."
              @click="toggleCategoryHistory"
            />
          </div>
          <div
            v-if="showHelp"
            class="absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50 w-56 rounded bg-amber-100 text-black text-[10px] leading-snug px-2 py-1 shadow-lg border border-amber-300"
            @click.stop
          >
            Нажмите, чтобы посмотреть динамику просмотров по всем каналам
          </div>
        </div>
        <span>{{ page.category?.title || page.category?.name }}</span>
      </h2>

      <div
        v-if="showCategoryHistory"
        class="mb-4 p-2 shadow-lg bg-gray-50 rounded-lg text-black space-y-3"
      >
        <div class="text-xs">
          <div class="font-medium text-sm mb-1">
            Топ новых видео категории
            <span v-if="viewPeriod" class="font-normal text-gray-500">
              · {{ formattedDate(viewPeriod) }}
            </span>
          </div>
          <div
            v-if="categoryTopVideosLoading && !categoryTopVideos?.length"
            class="flex items-center gap-2 p-2 text-gray-500"
          >
            <span
              class="inline-block h-4 w-4 rounded-full border-2 border-gray-300 border-t-blue-500 animate-spin"
            />
            Загрузка видео…
          </div>
          <div v-else-if="categoryTopVideosError" class="p-2 text-red-600">
            {{ categoryTopVideosError }}
          </div>
          <div v-else-if="!categoryTopVideos?.length" class="p-2 text-gray-500">
            Нет новых видео за период
          </div>
          <div v-else>
            <VideoInfo
              v-for="(video, index) in visibleCategoryTopVideos"
              :key="video.video_id"
              :video="video"
              :index="index"
            />
            <button
              v-if="canExpandCategoryTopVideos"
              type="button"
              class="mt-1 mb-0.5 mx-auto block px-2 py-0.5 text-xs text-gray-500 hover:text-black hover:underline"
              title="Показать ещё 5 видео"
              @click="expandCategoryTopVideos"
            >
              еще 5
            </button>
          </div>
        </div>

        <div class="flex items-center gap-1 border-t border-gray-200 pt-2">
          <button
            type="button"
            class="shrink-0 self-stretch flex items-center px-0.5 hover:bg-black/5 rounded"
            :title="
              categoryHistoryMonths === 12
                ? 'Показать 24 месяца'
                : 'Вернуть 12 месяцев'
            "
            :aria-label="
              categoryHistoryMonths === 12
                ? 'Показать 24 месяца'
                : 'Вернуть 12 месяцев'
            "
            @click="toggleCategoryHistoryMonths"
          >
            <img
              src="/img/arrowLeft.svg"
              class="h-4"
              :class="categoryHistoryMonths === 24 ? 'rotate-180' : ''"
              alt=""
            />
          </button>
          <div class="min-w-0 flex-1">
            <ChannelHistory
              score-only
              :title="`Сумма индекса ${limit >= 999 ? 'всех' : `топ-${limit}`} (${categoryHistoryMonths} мес.)`"
              :points="categoryHistory || []"
              :loading="categoryHistoryLoading"
              :error="categoryHistoryError"
            />
          </div>
        </div>
      </div>

      <p v-if="archivePending" class="text-center text-sm opacity-70">Загрузка периода…</p>
      <p v-else-if="archiveError" class="text-center text-sm text-red-400">{{ archiveError }}</p>

      <Chart
        :data="chartData"
        :selected-sort="selectedSort"
        :period="viewPeriod"
        :limit="limit"
        :show-help="showHelp"
      />
    </div>

    <InfoBlock header="Предложить свой канал или тему" class="text-lg mt-3">
      <ClientOnly>
        <FeedbackForm />
      </ClientOnly>
    </InfoBlock>
  </div>
</template>
