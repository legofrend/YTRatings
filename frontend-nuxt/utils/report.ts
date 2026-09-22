/** Map flat video_stat row → UI VideoInfo shape. */
export function mapVideo(v: Record<string, any>) {
  return {
    video_id: v.video_id,
    channel_id: v.channel_id,
    channel_title: v.channel_title,
    custom_url: v.custom_url,
    title: v.title,
    is_short: v.is_short ? 1 : 0,
    is_clickbait: v.is_clickbait ? 1 : 0,
    clickbait_comment: v.clickbait_comment,
    video_url: v.video_url,
    thumbnail_url: v.thumbnail_url,
    published_at: v.published_at,
    stat: {
      duration: v.duration,
      score: v.score,
      view_count: v.period_view_count,
      like_count: v.period_like_count,
      comment_count: v.period_comment_count,
    },
  }
}

/** Map flat channel_stat row → UI shape with nested `stat`. */
export function mapChannel(ch: Record<string, any>) {
  const viewCount = ch.pv_view || 0
  const likeShare = viewCount > 0 ? ((ch.pv_like || 0) / viewCount) * 100 : 0
  const commentShare =
    viewCount > 0 ? ((ch.pv_comment || 0) / viewCount) * 100 : 0

  const topVideos = Array.isArray(ch.top_videos)
    ? ch.top_videos.map(mapVideo)
    : null

  return {
    channel_id: ch.channel_id,
    channel_title: ch.channel_title,
    description: ch.description || '',
    custom_url: ch.custom_url,
    thumbnail_url: ch.thumbnail_url,
    category_id: ch.category_id,
    category_name: ch.category_name || null,
    rank: ch.rank,
    rank_change: ch.rank_change != null ? -ch.rank_change : 0,
    top_videos: topVideos as any[] | null,
    force_expanded: !!ch.force_expanded || ch.channel_id === '__search_videos__',
    videos_loading: false,
    videos_error: null as string | null,
    history: null as any[] | null,
    history_loading: false,
    history_error: null as string | null,
    stat: {
      videos: ch.pv_video_long,
      video_clickbaits: null,
      shorts: ch.pv_video_short,
      duration: ch.pv_duration || 0,
      score: ch.pv_score,
      score_change: ch.pv_score_change,
      view_count: ch.pv_view,
      view_count_new_video: ch.pv_view_new_long,
      view_count_new_short: ch.pv_view_new_short,
      view_count_old_video: ch.pv_view_old_long,
      view_count_old_short: ch.pv_view_old_short,
      total_view_count_change: ch.pc_view,
      view_count_check: null,
      like_count: ch.pv_like,
      comment_count: ch.pv_comment,
      subscriber_count: ch.subscriber_count,
      subscriber_count_change: ch.pc_subscriber,
      like_share: likeShare,
      comment_share: commentShare,
    },
  }
}

export function formattedDate(dateStr: string | null | undefined) {
  if (!dateStr) return ''
  const dateObject = new Date(dateStr)
  const months = [
    'Январь',
    'Февраль',
    'Март',
    'Апрель',
    'Май',
    'Июнь',
    'Июль',
    'Август',
    'Сентябрь',
    'Октябрь',
    'Ноябрь',
    'Декабрь',
  ]
  return `${months[dateObject.getMonth()]} ${dateObject.getFullYear()}`
}

export function channelsScale(channels: ReturnType<typeof mapChannel>[]) {
  const top = channels[0]
  if (!top) return 0
  return top.stat.score + Math.max(0, -(top.stat.score_change || 0))
}

export type Category = {
  id: number
  name: string
  title?: string
  description?: string | null
  sys_name?: string | null
  sort_order?: number
}
