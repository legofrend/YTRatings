<script setup lang="ts">
import {
  channelsScale,
  formattedDate,
  mapChannel,
  mapVideo,
  aggregateChannelStats,
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
  search: searchApi,
  wordstat: fetchWordstat,
} = useYtrApi()

const sysName = computed(() => String(route.params.sysName || ''))
const periodQuery = computed(() => {
  const p = route.query.period
  return typeof p === 'string' && p ? p : null
})
const limit = computed(() => {
  const n = Number(route.query.limit)
  if (!Number.isFinite(n) || n <= 0) return 20
  if (n >= 999) return 100 // legacy «все» → топ 100 + pagination
  return Math.min(n, 100)
})
/** Cap for API / category aggregate (backend max 100). */
const apiLimit = computed(() => limit.value)

const listPage = computed(() => {
  const n = Number(route.query.page)
  if (!Number.isFinite(n) || n < 1) return 1
  return Math.floor(n)
})

const selectedSort = ref('rank')
const sortTypes = [
  { id: 'rank', name: 'Место' },
  { id: 'subscriber_count', name: 'Подписчики' },
  { id: 'like_share', name: 'Доля лайков' },
  { id: 'comment_share', name: 'Доля комментариев' },
  { id: 'duration', name: 'Длительность' },
]
/** Client filter over loaded channels (title / @handle). No API. */
const channelFilter = ref('')
const inlineSearch = ref<{
  query: string
  period: string
  fallback: boolean
  channels: ReturnType<typeof mapChannel>[]
  scale: number
} | null>(null)
const searchPending = ref(false)
const searchError = ref<string | null>(null)

function normFilter(s: string) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/^@+/, '')
}

watch(sysName, () => {
  channelFilter.value = ''
  inlineSearch.value = null
  searchError.value = null
})

async function runBackendSearch() {
  const q = channelFilter.value.trim()
  if (!q || searchPending.value) return

  const catId = page.value?.category?.id
  if (catId == null) return

  searchPending.value = true
  searchError.value = null
  try {
    const res = await searchApi({
      query: q,
      category_id: catId,
      period: activePeriod.value,
      limit_ch: 50,
    })
    const channels = (res.channels || [])
      .filter((c) => c.channel_id !== '__search_videos__')
      .map(mapChannel)
    inlineSearch.value = {
      query: q,
      period: res.period,
      fallback: !!res.category_fallback,
      channels,
      scale: channelsScale(channels),
    }
  } catch (err: any) {
    console.warn('[search]', err)
    inlineSearch.value = null
    searchError.value = 'failed'
  } finally {
    searchPending.value = false
  }
}

function clearInlineSearch() {
  inlineSearch.value = null
  searchError.value = null
}

watch(channelFilter, () => {
  if (inlineSearch.value) clearInlineSearch()
})

/** SSG payload: category + latest period channels (SEO). Soft-404 keeps toolbar. */
const { data: page, error, pending, refresh: refreshPage } = await useAsyncData(
  () => `cat-${sysName.value}`,
  async () => {
    const cats = (await fetchCategories()) as Category[]
    const categories = cats.filter((c) => c.id !== 0 && c.sys_name)
    const cat = cats.find((c) => c.sys_name === sysName.value)

    if (!cat) {
      return {
        categories,
        category: null as Category | null,
        periods: [] as string[],
        latestPeriod: null as string | null,
        period: null as string | null,
        scale: 0,
        total: 0,
        channels: [] as ReturnType<typeof mapChannel>[],
        missing: 'category' as const,
      }
    }

    const { periods } = await fetchPeriods(cat.id)
    if (!periods.length) {
      return {
        categories,
        category: cat,
        periods: [] as string[],
        latestPeriod: null as string | null,
        period: null as string | null,
        scale: 0,
        total: 0,
        channels: [] as ReturnType<typeof mapChannel>[],
        missing: 'periods' as const,
      }
    }
    const latestPeriod = periods[0]
    const res = await fetchChannels(cat.id, latestPeriod, {
      limit: 100,
      offset: 0,
      videos: true,
    })
    const channels = (res.channels || []).map(mapChannel)

    return {
      categories,
      category: cat,
      periods,
      latestPeriod,
      period: res.period,
      scale: channelsScale(channels),
      total: res.total ?? channels.length,
      channels,
      missing: null as null,
    }
  },
  {
    watch: [sysName],
    getCachedData(key, nuxtApp) {
      return nuxtApp.payload.data[key] ?? nuxtApp.static.data[key]
    },
  }
)

// Must stay in setup (not inside useAsyncData fetcher — loses Nuxt context after await).
if (import.meta.server && page.value?.missing) {
  setResponseStatus(404)
}

const pageMissing = computed(() => page.value?.missing ?? null)
const missingMessage = computed(() => {
  if (pageMissing.value === 'category') {
    return `Категория «${sysName.value}» не найдена. Выберите другую в списке.`
  }
  if (pageMissing.value === 'periods') {
    return 'Для этой категории пока нет данных.'
  }
  return null
})

/** Query period only if it exists for this category; else null → latest. */
const validPeriodQuery = computed(() => {
  const q = periodQuery.value
  const periods = page.value?.periods
  if (!q || !periods?.length) return null
  return periods.includes(q) ? q : null
})

const isArchive = computed(() => {
  if (!page.value || !validPeriodQuery.value) return false
  return validPeriodQuery.value !== page.value.latestPeriod
})

const activePeriod = computed(
  () => validPeriodQuery.value || page.value?.latestPeriod || null
)

const RANKING_CHUNK = 100

type RankingState = {
  key: string
  categoryId: number
  period: string
  total: number
  channels: ReturnType<typeof mapChannel>[]
}
/** Client ranking buffer (seeded from SSG / archive fetch; grows past 100). */
const ranking = ref<RankingState | null>(null)
const rankingPending = ref(false)
const rankingError = ref<string | null>(null)
/** Bumped on nav / new ensure — stale in-flight fetches must not write back. */
let rankingFetchId = 0

function rankingKey(categoryId: number, period: string) {
  return `${categoryId}:${period}`
}

function seedRankingFromPage() {
  const catId = page.value?.category?.id
  const period = page.value?.latestPeriod
  if (catId == null || !period || !page.value?.channels) return
  if (page.value.category?.sys_name !== sysName.value) return
  ranking.value = {
    key: rankingKey(catId, period),
    categoryId: catId,
    period,
    total: page.value.total || page.value.channels.length,
    channels: [...page.value.channels],
  }
}

async function ensureRankingThrough(needThrough: number) {
  const catId = page.value?.category?.id
  const period = activePeriod.value
  if (catId == null || !period) return
  if (page.value?.category?.sys_name !== sysName.value) return

  const fetchId = ++rankingFetchId
  const stillCurrent = () =>
    fetchId === rankingFetchId &&
    page.value?.category?.id === catId &&
    activePeriod.value === period

  const key = rankingKey(catId, period)
  let state = ranking.value
  if (!state || state.key !== key) {
    if (
      !isArchive.value &&
      page.value?.channels?.length &&
      page.value.latestPeriod === period &&
      page.value.category?.id === catId
    ) {
      seedRankingFromPage()
      state = ranking.value
    } else {
      rankingPending.value = true
      rankingError.value = null
      try {
        const res = await fetchChannels(catId, period, {
          limit: RANKING_CHUNK,
          offset: 0,
          videos: true,
        })
        if (!stillCurrent()) return
        const channels = (res.channels || []).map(mapChannel)
        ranking.value = {
          key,
          categoryId: catId,
          period: res.period,
          total: res.total ?? channels.length,
          channels,
        }
        state = ranking.value
      } catch (err: any) {
        if (!stillCurrent()) return
        console.warn('[ranking]', err)
        ranking.value = null
        rankingError.value = 'failed'
        return
      } finally {
        if (fetchId === rankingFetchId) rankingPending.value = false
      }
    }
  }
  if (!state || !stillCurrent()) return

  const target = Math.min(
    Math.max(0, needThrough),
    state.total || needThrough
  )
  while (state.channels.length < target) {
    if (!stillCurrent()) return
    rankingPending.value = true
    rankingError.value = null
    try {
      const offset = state.channels.length
      const res = await fetchChannels(catId, period, {
        limit: RANKING_CHUNK,
        offset,
        videos: false,
      })
      if (!stillCurrent()) return
      const more = (res.channels || []).map(mapChannel)
      if (res.total != null) state.total = res.total
      if (!more.length) break
      // append only new ids (guard overlap)
      const seen = new Set(state.channels.map((c) => c.channel_id))
      for (const ch of more) {
        if (!seen.has(ch.channel_id)) state.channels.push(ch)
      }
      ranking.value = { ...state, channels: [...state.channels] }
      state = ranking.value
      if (more.length < RANKING_CHUNK) break
    } catch (err: any) {
      if (!stillCurrent()) return
      console.warn('[ranking]', err)
      rankingError.value = 'failed'
      break
    } finally {
      if (fetchId === rankingFetchId) rankingPending.value = false
    }
  }
}

async function retryRanking() {
  rankingError.value = null
  ranking.value = null
  const need = listPage.value * limit.value
  await ensureRankingThrough(Math.max(need, limit.value, RANKING_CHUNK))
}

async function retryPage() {
  await refreshPage()
  if (page.value && !error.value) await retryRanking()
}

watch(
  [
    () => page.value?.category?.id,
    activePeriod,
    listPage,
    limit,
    () => page.value?.channels,
  ],
  async ([catId, period]) => {
    if (catId == null || !period) {
      ranking.value = null
      rankingError.value = null
      return
    }
    if (!import.meta.client && !isArchive.value) {
      seedRankingFromPage()
      return
    }
    if (!import.meta.client) return

    const need = listPage.value * limit.value
    // also keep top-N for category aggregate
    await ensureRankingThrough(Math.max(need, limit.value, RANKING_CHUNK))
  },
  { immediate: true }
)

const viewChannels = computed(() => {
  if (inlineSearch.value) return inlineSearch.value.channels
  // never show ranking from another category/period
  if (rankingReady.value && ranking.value?.channels?.length) {
    return ranking.value.channels
  }
  // SSG/page payload only if it matches the route (avoid flash of previous cat)
  if (page.value?.category?.sys_name === sysName.value) {
    return page.value.channels || []
  }
  return []
})
const viewScale = computed(() => {
  if (inlineSearch.value) return inlineSearch.value.scale
  return channelsScale(viewChannels.value)
})
const viewPeriod = computed(() => {
  if (inlineSearch.value) return inlineSearch.value.period
  if (rankingReady.value && ranking.value?.period) return ranking.value.period
  if (page.value?.category?.sys_name === sysName.value) {
    return page.value.period || activePeriod.value
  }
  return activePeriod.value
})
const rankingTotal = computed(() => {
  if (inlineSearch.value) return inlineSearch.value.channels.length
  if (rankingReady.value && ranking.value) {
    return ranking.value.total || ranking.value.channels.length
  }
  if (page.value?.category?.sys_name === sysName.value) {
    return page.value.total || page.value.channels?.length || 0
  }
  return 0
})

/** True when ranking buffer matches current category + period. */
const rankingReady = computed(() => {
  const catId = page.value?.category?.id
  const period = activePeriod.value
  if (catId == null || !period) return false
  if (page.value?.category?.sys_name !== sysName.value) return false
  const r = ranking.value
  return !!r && r.key === rankingKey(catId, period)
})

/**
 * Overlay while category/period nav catches up. Cleared only when page +
 * ranking match the target (not when the *previous* ranking still looks
 * "ready").
 */
const navLoading = ref(false)
let navLoadingSince = 0
const NAV_LOADING_MIN_MS = 280

function beginNavLoading() {
  if (!import.meta.client) return
  navLoading.value = true
  navLoadingSince = Date.now()
  // invalidate in-flight ranking + drop stale buffer so wait can't
  // succeed on the previous cat/period
  rankingFetchId++
  ranking.value = null
  rankingError.value = null
  rankingPending.value = false
}

async function endNavLoading() {
  if (!navLoading.value) return
  const left = NAV_LOADING_MIN_MS - (Date.now() - navLoadingSince)
  if (left > 0) await new Promise((r) => setTimeout(r, left))
  navLoading.value = false
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

/**
 * Wait until route page payload and ranking buffer match the nav target.
 * `periodQuery` null → latest period for that category.
 */
async function waitNavContentReady(
  target: { sysName: string; periodQuery: string | null },
  timeoutMs = 15000
) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const p = page.value
    const catOk = p?.category?.sys_name === target.sysName
    const routeOk = sysName.value === target.sysName
    if (catOk && routeOk && !pending.value) {
      const periods = p?.periods || []
      const wantPeriod =
        target.periodQuery && periods.includes(target.periodQuery)
          ? target.periodQuery
          : p?.latestPeriod || null
      const catId = p?.category?.id
      const r = ranking.value
      const rankingOk =
        catId != null &&
        !!wantPeriod &&
        !!r &&
        r.key === rankingKey(catId, wantPeriod) &&
        !rankingPending.value
      if (rankingOk) return
      // hard fail: ranking gave up
      if (rankingError.value && !r) return
    }
    await sleep(40)
  }
}

const contentLoading = computed(() => {
  if (pageMissing.value || inlineSearch.value) return false
  return navLoading.value
})

/** Rating list (not backend-search results) for local filter / empty check. */
const ratingChannelsForFilter = computed(() => viewChannels.value)

/** Local filter only when not showing backend search results. */
const chartFilterQuery = computed(() =>
  inlineSearch.value ? '' : channelFilter.value
)

const localFilterMatches = computed(() => {
  const q = normFilter(channelFilter.value)
  const list = ratingChannelsForFilter.value
  if (!q) return list
  return list.filter((c) => {
    const title = String(c.channel_title || '').toLowerCase()
    const handle = normFilter(c.custom_url || '')
    return title.includes(q) || handle.includes(q)
  })
})

/** category_id → sys_name for clickable category hints in search results. */
const categorySysById = computed(() => {
  const m: Record<number, string> = {}
  for (const c of page.value?.categories || []) {
    if (c.id != null && c.sys_name) m[c.id] = c.sys_name
  }
  return m
})

/** Enter / filter icon: escalate to API only when local filter found nothing. */
async function onFilterAction() {
  const q = channelFilter.value.trim()
  if (!q || searchPending.value) return
  if (!inlineSearch.value && localFilterMatches.value.length > 0) return
  await runBackendSearch()
}

function onFilterKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter') return
  e.preventDefault()
  onFilterAction()
}

const chartData = computed(() => ({
  category: page.value?.category || null,
  period: viewPeriod.value,
  scale: viewScale.value,
  data: viewChannels.value,
}))

/** Same set Chart shows (filter + sort + limit) → category header sums. */
const categoryStatChannels = computed(() => {
  let channels = [...viewChannels.value]
  const q = normFilter(chartFilterQuery.value)
  if (q) {
    channels = channels.filter((c) => {
      const title = String(c.channel_title || '').toLowerCase()
      const handle = normFilter(c.custom_url || '')
      return title.includes(q) || handle.includes(q)
    })
  }
  if (selectedSort.value && selectedSort.value !== 'rank') {
    const key = selectedSort.value
    channels.sort((a, b) => {
      const v1 = a.stat?.[key]
      const v2 = b.stat?.[key]
      if (typeof v1 === 'number' && typeof v2 === 'number') return v2 - v1
      return 0
    })
  }
  const lim =
    inlineSearch.value
      ? channels.length
      : Math.min(limit.value, channels.length)
  return channels.slice(0, lim)
})

const categoryAggregateStat = computed(() =>
  aggregateChannelStats(categoryStatChannels.value)
)

const pagePending = computed(
  () =>
    (pending.value && !page.value) ||
    (rankingPending.value && !viewChannels.value.length)
)
/** Truthy when initial page fetch failed (no payload). */
const pageFetchFailed = computed(() => !!error.value && !page.value)
/** Ranking failed and nothing to show yet. */
const rankingFetchFailed = computed(
  () => !!rankingError.value && !viewChannels.value.length
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
    if (validPeriodQuery.value) q.set('period', validPeriodQuery.value)
    if (limit.value !== 20) q.set('limit', String(limit.value))
    if (listPage.value > 1) q.set('page', String(listPage.value))
    const qs = q.toString()
    return `${config.public.siteUrl}/${slug}${qs ? `?${qs}` : ''}`
  },
})

useHead({
  meta: [{ name: 'keywords', content: seoKeywords }],
})

function ratingQuery(opts: {
  period?: string | null
  limit?: number
  page?: number | null
}) {
  const q: Record<string, string> = {}
  const period = opts.period
  const lim = opts.limit ?? limit.value
  const latest = page.value?.latestPeriod
  if (period && period !== latest) q.period = period
  if (lim !== 20) q.limit = String(lim)
  const p = opts.page ?? listPage.value
  if (p != null && p > 1) q.page = String(p)
  return q
}

/** Drop stale ?period= when switching to a category that lacks that month. */
watch(
  [periodQuery, () => page.value?.periods, sysName],
  ([q, periods]) => {
    if (!import.meta.client || !q || !periods?.length) return
    if (periods.includes(q)) return
    navigateTo(
      {
        path: `/${sysName.value}`,
        query: ratingQuery({ period: null, page: 1 }),
      },
      { replace: true }
    )
  },
  { immediate: true }
)

async function changeCategory(nextSysName: string) {
  if (!nextSysName || nextSysName === sysName.value) return
  const periodQ = periodQuery.value
  beginNavLoading()
  try {
    await navigateTo({
      path: `/${nextSysName}`,
      query: ratingQuery({ period: periodQ, page: 1 }),
    })
    await waitNavContentReady({ sysName: nextSysName, periodQuery: periodQ })
  } finally {
    await endNavLoading()
  }
}

async function changePeriod(period: string) {
  if (!period || period === activePeriod.value) return
  beginNavLoading()
  try {
    await navigateTo({
      path: `/${sysName.value}`,
      query: ratingQuery({ period, page: 1 }),
    })
    await waitNavContentReady({
      sysName: sysName.value,
      periodQuery: period,
    })
  } finally {
    await endNavLoading()
  }
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
    query: ratingQuery({
      period: validPeriodQuery.value,
      limit: n,
      page: 1,
    }),
  })
}

async function changeListPage(n: number) {
  if (!n || n === listPage.value) return
  await navigateTo({
    path: `/${sysName.value}`,
    query: ratingQuery({ period: validPeriodQuery.value, page: n }),
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
    console.warn('[categoryHistory]', err)
    categoryHistory.value = null
    categoryHistoryError.value = 'failed'
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
    console.warn('[categoryTopVideos]', err)
    categoryTopVideos.value = null
    categoryTopVideosError.value = 'failed'
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

type WordstatReport = {
  leaving: { lexeme: string; word: string; freq: number; type: number | null }[]
  core: { lexeme: string; word: string; freq: number; type: number | null }[]
  ['new']: { lexeme: string; word: string; freq: number; type: number | null }[]
}
const wordstatReport = ref<WordstatReport | null>(null)
const wordstatKey = ref('')

const hasWordstat = computed(() => {
  const r = wordstatReport.value
  if (!r) return false
  return r.leaving.length + r.core.length + r.new.length > 0
})

async function loadWordstat() {
  const catId = page.value?.category?.id
  const period = viewPeriod.value
  if (catId == null || !period) {
    wordstatReport.value = null
    wordstatKey.value = ''
    return
  }
  const key = `${catId}|${period}`
  if (key === wordstatKey.value && wordstatReport.value) return
  try {
    const res = await fetchWordstat(catId, period)
    wordstatReport.value = {
      leaving: res.leaving || [],
      core: res.core || [],
      new: res.new || [],
    }
    wordstatKey.value = key
  } catch {
    wordstatReport.value = null
    wordstatKey.value = ''
  }
}

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
  wordstatReport.value = null
  wordstatKey.value = ''
})

watch(
  [() => page.value?.category?.id, viewPeriod],
  () => {
    loadWordstat()
  },
  { immediate: true }
)

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
    <div
      v-else-if="pageFetchFailed"
      class="mx-auto max-w-md px-4 py-8"
    >
      <UIFetchError
        message="Не удалось загрузить рейтинг"
        @retry="retryPage"
      />
    </div>
    <div v-else-if="page">
      <div
        class="relative flex flex-wrap justify-center items-center gap-x-3 gap-y-2 py-1 select-none"
      >
        <div class="relative shrink-0">
          <select
            :value="page.category?.sys_name || ''"
            class="pl-1 text-black text-base cursor-pointer rounded max-w-[min(100%,16rem)]"
            name="category"
            :disabled="contentLoading"
            @change="changeCategory(($event.target as HTMLSelectElement).value)"
          >
            <option
              v-if="pageMissing === 'category'"
              disabled
              value=""
            >
              — не найдена: {{ sysName }} —
            </option>
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

        <template v-if="!pageMissing">
          <select
            :value="limit"
            name="topChannels"
            class="text-black text-base cursor-pointer rounded shrink-0"
            :disabled="contentLoading"
            @change="changeLimit(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="n in topNumbers" :key="n.value" :value="n.value">
              {{ n.name }}
            </option>
          </select>

          <div class="relative flex justify-center items-center select-none gap-1 shrink-0">
            <img
              src="/img/arrowLeftWhite.svg"
              class="h-4 mx-1 cursor-pointer"
              :class="contentLoading ? 'opacity-40 pointer-events-none' : ''"
              alt=""
              @click="shiftPeriod(-1)"
            />
            <select
              :value="activePeriod || ''"
              class="text-black text-base cursor-pointer rounded"
              name="period"
              :disabled="contentLoading"
              @change="changePeriod(($event.target as HTMLSelectElement).value)"
            >
              <option v-for="p in page.periods" :key="p" :value="p">
                {{ formattedDate(p) }}
              </option>
            </select>
            <img
              src="/img/arrowLeftWhite.svg"
              class="h-4 mx-1 cursor-pointer rotate-180"
              :class="contentLoading ? 'opacity-40 pointer-events-none' : ''"
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

          <div class="relative flex flex-row items-center gap-1 shrink-0">
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

          <div class="relative flex flex-row items-center gap-1 shrink-0">
            <button
              type="button"
              class="bg-white rounded-lg h-5 w-7 items-center flex justify-center shrink-0 hover:bg-gray-100 disabled:opacity-50"
              title="Искать в API, если локально пусто (Enter)"
              :disabled="searchPending || !channelFilter.trim()"
              @click="onFilterAction"
            >
              <img src="/img/filter.svg" class="h-3.5" alt="" />
            </button>
            <input
              v-model="channelFilter"
              type="search"
              name="channelFilter"
              placeholder="фильтр…"
              autocomplete="off"
              class="text-black text-base rounded w-28 md:w-40 px-1 min-w-0"
              @keydown="onFilterKeydown"
            />
          </div>
        </template>

        <div class="relative shrink-0">
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

      <p
        v-if="missingMessage"
        class="text-center text-base md:text-lg py-10 px-4 text-white/90"
      >
        {{ missingMessage }}
      </p>

      <template v-else>
      <!-- rating body: dim + spinner while category/period data catches up -->
      <div class="relative w-full min-w-0">
        <div
          class="transition-opacity duration-150"
          :class="contentLoading ? 'opacity-40 pointer-events-none select-none' : ''"
          :aria-busy="contentLoading ? 'true' : undefined"
        >
      <!-- category bar: same left edge as content (no negative margin → no clip) -->
      <div class="w-full min-w-0">
        <CategoryItem
          :title="page.category?.title || page.category?.name || ''"
          :description="page.category?.description"
          :stat="categoryAggregateStat"
          :expanded="showCategoryHistory"
          :show-help="showHelp"
          @toggle="toggleCategoryHistory"
        >
          <Wordstat
            v-if="hasWordstat && wordstatReport"
            :report="wordstatReport"
            :category-id="page.category?.id"
            :period="viewPeriod"
          />

          <div
            class="text-xs"
            :class="hasWordstat ? 'border-t border-gray-200 pt-2' : ''"
          >
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
            <UIFetchError
              v-else-if="categoryTopVideosError"
              compact
              message="Не удалось загрузить видео"
              @retry="loadCategoryTopVideos(true)"
            />
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
                :title="`Сумма индекса топ-${limit} (${categoryHistoryMonths} мес.)`"
                :points="categoryHistory || []"
                :loading="categoryHistoryLoading"
                :error="categoryHistoryError"
                @retry="loadCategoryHistory(true)"
              />
            </div>
          </div>
        </CategoryItem>
      </div>

      <div
        v-if="rankingFetchFailed"
        class="mx-auto max-w-md py-4"
      >
        <UIFetchError
          message="Не удалось загрузить список каналов"
          @retry="retryRanking"
        />
      </div>

      <div
        v-if="inlineSearch || searchPending || searchError"
        class="flex flex-wrap items-center justify-center gap-2 text-sm py-2"
      >
        <span v-if="searchPending" class="opacity-70">Поиск…</span>
        <div v-else-if="searchError" class="w-full max-w-sm">
          <UIFetchError
            compact
            message="Поиск не удался"
            @retry="runBackendSearch"
          />
        </div>
        <template v-else-if="inlineSearch">
          <span>
            Поиск «{{ inlineSearch.query }}»:
            {{ inlineSearch.channels.length }} каналов
            <span v-if="inlineSearch.fallback" class="text-gray-400">
              (в категории пусто → все категории)
            </span>
          </span>
          <button
            type="button"
            class="underline opacity-80 hover:opacity-100"
            @click="clearInlineSearch"
          >
            сбросить
          </button>
        </template>
      </div>

      <Chart
        :data="chartData"
        :selected-sort="selectedSort"
        :period="viewPeriod"
        :limit="inlineSearch ? 999 : limit"
        :page="inlineSearch ? 1 : listPage"
        :total="inlineSearch ? inlineSearch.channels.length : rankingTotal"
        :loading-more="rankingPending && rankingReady"
        :filter-query="chartFilterQuery"
        :page-category-id="page?.category?.id ?? null"
        :category-sys-by-id="categorySysById"
        :show-help="showHelp && !inlineSearch"
        @change-page="changeListPage"
      />
        </div>

        <div
          v-if="contentLoading"
          class="absolute inset-0 z-10 flex items-start justify-center pt-24 md:pt-32 pointer-events-none"
          aria-live="polite"
          aria-label="Загрузка"
        >
          <div
            class="flex items-center gap-2 rounded-lg bg-black/70 text-white text-sm px-3 py-2 shadow-lg"
          >
            <span
              class="inline-block h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin"
            />
            Загрузка…
          </div>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>
