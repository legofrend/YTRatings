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

/** Map flat channel_rating row → UI shape with nested `stat`. */
export function mapChannel(ch: Record<string, any>) {
  const viewCount = ch.video_views || 0
  const likeShare = viewCount > 0 ? ((ch.video_likes || 0) / viewCount) * 100 : 0
  const commentShare =
    viewCount > 0 ? ((ch.video_comments || 0) / viewCount) * 100 : 0

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
    // UI: positive = rose in ranking (lower rank number)
    rank_change: ch.rank_mom != null ? -ch.rank_mom : 0,
    top_videos: topVideos as any[] | null,
    force_expanded: !!ch.force_expanded || ch.channel_id === '__search_videos__',
    videos_loading: false,
    videos_error: null as string | null,
    history: null as any[] | null,
    history_loading: false,
    history_error: null as string | null,
    stat: {
      videos: ch.new_longs,
      video_clickbaits: null,
      shorts: ch.new_shorts,
      duration: ch.duration_sec || 0,
      score: ch.score,
      score_change: ch.score_mom,
      view_count: ch.video_views,
      view_count_new_video: ch.views_new_long,
      view_count_new_short: ch.views_new_short,
      view_count_old_video: ch.views_old_long,
      view_count_old_short: ch.views_old_short,
      total_view_count_change: ch.channel_views_mom,
      view_count_check: null,
      like_count: ch.video_likes,
      comment_count: ch.video_comments,
      subscriber_count: ch.channel_subscribers,
      subscriber_count_change: ch.channel_subscribers_mom,
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

/** Sum channel stats for category header (shares from totals). */
export function aggregateChannelStats(
  channels: ReturnType<typeof mapChannel>[]
) {
  let score = 0
  let score_change = 0
  let subscriber_count = 0
  let subscriber_count_change = 0
  let videos = 0
  let shorts = 0
  let duration = 0
  let view_count = 0
  let view_count_new_video = 0
  let view_count_new_short = 0
  let view_count_old_video = 0
  let view_count_old_short = 0
  let like_count = 0
  let comment_count = 0

  for (const ch of channels) {
    const s = ch.stat || ({} as any)
    score += Number(s.score) || 0
    score_change += Number(s.score_change) || 0
    subscriber_count += Number(s.subscriber_count) || 0
    subscriber_count_change += Number(s.subscriber_count_change) || 0
    videos += Number(s.videos) || 0
    shorts += Number(s.shorts) || 0
    duration += Number(s.duration) || 0
    view_count += Number(s.view_count) || 0
    view_count_new_video += Number(s.view_count_new_video) || 0
    view_count_new_short += Number(s.view_count_new_short) || 0
    view_count_old_video += Number(s.view_count_old_video) || 0
    view_count_old_short += Number(s.view_count_old_short) || 0
    like_count += Number(s.like_count) || 0
    comment_count += Number(s.comment_count) || 0
  }

  const like_share = view_count > 0 ? (like_count / view_count) * 100 : 0
  const comment_share = view_count > 0 ? (comment_count / view_count) * 100 : 0

  return {
    videos,
    video_clickbaits: null,
    shorts,
    duration,
    score,
    score_change,
    view_count,
    view_count_new_video,
    view_count_new_short,
    view_count_old_video,
    view_count_old_short,
    total_view_count_change: null,
    view_count_check: null,
    like_count,
    comment_count,
    subscriber_count,
    subscriber_count_change,
    like_share,
    comment_share,
  }
}

export type Category = {
  id: number
  name: string
  title?: string
  description?: string | null
  sys_name?: string | null
  sort_order?: number
}
