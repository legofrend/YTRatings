export function useYtrApi() {
  const config = useRuntimeConfig()
  // server (SSG/SSR): private apiBase; client: public
  const base = import.meta.server
    ? config.apiBase
    : config.public.apiBase

  function api<T>(path: string, opts: Parameters<typeof $fetch<T>>[1] = {}) {
    const url = path.startsWith('http')
      ? path
      : `${String(base).replace(/\/$/, '')}/${path.replace(/^\//, '')}`
    return $fetch<T>(url, opts)
  }

  return {
    api,
    categories: () => api<import('~/utils/report').Category[]>('categories'),
    periods: (categoryId: number) =>
      api<{ category_id: number; periods: string[] }>('periods', {
        query: { category_id: categoryId },
      }),
    channels: (categoryId: number, period: string, limit = 100) =>
      api<{
        category_id: number
        period: string
        limit: number
        channels: Record<string, any>[]
      }>('channels', {
        query: {
          category_id: categoryId,
          period,
          limit,
          // SSG / archive: top-5 videos for top-10 channels (instant expand)
          videos_limit: 5,
          videos_for: 10,
        },
      }),
    videos: (channelId: string, period: string, limit = 10) =>
      api<{ videos: Record<string, any>[] }>('videos', {
        query: { channel_id: channelId, period, limit },
      }),
    categoryVideos: (categoryId: number, period: string, limit = 5) =>
      api<{ videos: Record<string, any>[] }>('videos', {
        query: { category_id: categoryId, period, limit },
      }),
    channelDynamics: (channelId: string, months = 12) =>
      api<{ points: Record<string, any>[] }>('channel', {
        query: { channel_id: channelId, months },
      }),
    categoryDynamics: (categoryId: number, limit = 20, months = 12) =>
      api<{
        category_id: number
        limit: number
        months: number
        points: Record<string, any>[]
      }>('category', {
        query: { category_id: categoryId, limit, months },
      }),
  }
}
