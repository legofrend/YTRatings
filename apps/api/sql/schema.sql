-- YTRatings Postgres schema (source of truth for empty DB / disaster recovery).
-- Generated from live VPS DB via: docker exec o2t4_db pg_dump ... --schema-only
-- NOT loaded by the Python app at runtime (queries live in DAOs / FastAPI v2).
--
-- Apply on empty DB:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/schema.sql
--   # or: docker exec -i o2t4_db psql -U root -d ytr_db < sql/schema.sql
--
-- Excludes ephemeral/scratch objects (temporary ad-hoc tables).
--


--
-- PostgreSQL database dump
--

-- Dumped from database version 16.3 (Debian 16.3-1.pgdg120+1)
-- Dumped by pg_dump version 16.3 (Debian 16.3-1.pgdg120+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: backfill_video_title_tsv(integer); Type: PROCEDURE; Schema: public; Owner: -
--

CREATE PROCEDURE public.backfill_video_title_tsv(IN batch_size integer DEFAULT 5000)
    LANGUAGE plpgsql
    AS $$
DECLARE
  updated int;
  total int := 0;
BEGIN
  LOOP
    WITH cte AS (
      SELECT id
      FROM video
      WHERE title_tsv IS NULL
      ORDER BY id
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED
    )
    UPDATE video v
    SET title_tsv = to_tsvector('russian', coalesce(v.title, ''))
    FROM cte
    WHERE v.id = cte.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    EXIT WHEN updated = 0;
    total := total + updated;
    RAISE NOTICE 'backfill_video_title_tsv: +% (total %)', updated, total;
    COMMIT;
  END LOOP;
  RAISE NOTICE 'backfill_video_title_tsv: done, % rows', total;
END;
$$;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

--
-- Name: video_title_tsv_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.video_title_tsv_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.title_tsv := to_tsvector('russian', coalesce(NEW.title, ''));
  RETURN NEW;
END;
$$;


--
-- Name: channel_stat_set_pc(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.channel_stat_set_pc() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    prev_id integer;
    prev_views bigint;
    prev_subs bigint;
    prev_videos integer;
BEGIN
    SELECT id, channel_view_count, subscriber_count, video_count
      INTO prev_id, prev_views, prev_subs, prev_videos
      FROM public.channel_stat
     WHERE channel_id = NEW.channel_id
       AND report_period = (NEW.report_period - INTERVAL '1 month')::date
     ORDER BY id DESC
     LIMIT 1;

    IF prev_id IS NULL THEN
        NEW.ppcs_id := 0;
        NEW.pc_view := COALESCE(NEW.channel_view_count, 0);
        NEW.pc_subscriber := COALESCE(NEW.subscriber_count, 0);
        NEW.pc_video := COALESCE(NEW.video_count, 0);
    ELSE
        NEW.ppcs_id := prev_id;
        NEW.pc_view := COALESCE(NEW.channel_view_count, 0) - COALESCE(prev_views, 0);
        NEW.pc_subscriber := COALESCE(NEW.subscriber_count, 0) - COALESCE(prev_subs, 0);
        NEW.pc_video := COALESCE(NEW.video_count, 0) - COALESCE(prev_videos, 0);
    END IF;
    RETURN NEW;
END;
$$;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: category; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.category (
    active integer DEFAULT 1 NOT NULL,
    name character varying,
    title character varying,
    description character varying,
    id integer NOT NULL,
    sys_name character varying,
    sort_order integer DEFAULT 1000
);

--
-- Name: category_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.category_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.category_id_seq OWNED BY public.category.id;

--
-- Name: channel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channel (
    category_id integer,
    channel_id character varying NOT NULL,
    channel_title character varying NOT NULL,
    description character varying,
    published_at timestamp without time zone,
    thumbnail_url character varying,
    custom_url character varying,
    status integer,
    id integer NOT NULL,
    last_video_fetch_dt timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    data jsonb DEFAULT '{}'::jsonb,
    priority integer,
    last_shorts_fetch_dt timestamp without time zone
);

--
-- Name: COLUMN channel.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.channel.status IS '0 deleted, 1 active, 2 no videos 6m, 3 low views, 4 low subs, 5 wrong lang, 6 wrong cat, 7 manual off';

--
-- Name: channel_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.channel_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: channel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.channel_id_seq OWNED BY public.channel.id;

--
-- Name: video; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.video (
    video_id character varying NOT NULL,
    channel_id character varying NOT NULL,
    title character varying NOT NULL,
    description character varying,
    published_at timestamp without time zone NOT NULL,
    published_at_period date,
    video_url character varying,
    thumbnail_url character varying,
    duration integer,
    is_short boolean,
    is_clickbait boolean,
    clickbait_comment character varying,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    data jsonb DEFAULT '{}'::jsonb,
    status integer DEFAULT 1,
    rank integer,
    title_tsv tsvector
);

--
-- Name: video_stat; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.video_stat (
    video_id character varying NOT NULL,
    data_at timestamp without time zone NOT NULL,
    view_count bigint NOT NULL,
    like_count bigint NOT NULL,
    comment_count bigint NOT NULL,
    report_period date,
    prev_period date GENERATED ALWAYS AS ((report_period - '1 mon'::interval)) STORED NOT NULL,
    id integer NOT NULL,
    period_view_count bigint,
    period_like_count bigint,
    period_comment_count bigint,
    is_short boolean,
    is_new boolean,
    channel_id text,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: video_stat_change; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.video_stat_change AS
 SELECT c.category_id,
    cur.report_period,
    v.published_at_period AS published_period,
    v.channel_id,
    cur.video_id,
        CASE
            WHEN (v.is_clickbait = true) THEN 1
            ELSE 0
        END AS is_clickbait,
        CASE
            WHEN (cur.report_period = v.published_at_period) THEN 1
            ELSE 0
        END AS is_new,
        CASE
            WHEN v.is_short THEN 1
            ELSE 0
        END AS is_short,
    v.duration,
    cur.id AS cur_vs_id,
    prev.id AS prev_vs_id,
    (
        CASE
            WHEN (prev.video_id IS NOT NULL) THEN (cur.view_count - prev.view_count)
            WHEN (cur.report_period = v.published_at_period) THEN cur.view_count
            ELSE (0)::bigint
        END /
        CASE
            WHEN v.is_short THEN 10
            ELSE 1
        END) AS score,
        CASE
            WHEN (prev.video_id IS NOT NULL) THEN (cur.view_count - prev.view_count)
            WHEN (cur.report_period = v.published_at_period) THEN cur.view_count
            ELSE (0)::bigint
        END AS view_count,
        CASE
            WHEN (prev.video_id IS NOT NULL) THEN (cur.like_count - prev.like_count)
            WHEN (cur.report_period = v.published_at_period) THEN cur.like_count
            ELSE (0)::bigint
        END AS like_count,
        CASE
            WHEN (prev.video_id IS NOT NULL) THEN (cur.comment_count - prev.comment_count)
            WHEN (cur.report_period = v.published_at_period) THEN cur.comment_count
            ELSE (0)::bigint
        END AS comment_count,
    cur.view_count AS cur_view_count,
    prev.view_count AS prev_view_count,
    cur.like_count AS cur_like_count,
    prev.like_count AS prev_like_count,
    cur.comment_count AS cur_comment_count,
    prev.comment_count AS prev_comment_count
   FROM (((public.video_stat cur
     LEFT JOIN public.video v ON (((v.video_id)::text = (cur.video_id)::text)))
     LEFT JOIN public.video_stat prev ON (((prev.report_period = cur.prev_period) AND ((prev.video_id)::text = (cur.video_id)::text))))
     LEFT JOIN public.channel c ON (((c.channel_id)::text = (v.channel_id)::text)))
  WHERE ((v.channel_id IS NOT NULL) AND (c.status > 0))
  ORDER BY c.category_id, cur.report_period, v.published_at_period;

--
-- Name: video_stat_subgroup; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.video_stat_subgroup AS
 SELECT category_id,
    report_period,
    channel_id,
    published_period,
    is_new,
    is_short,
    count(*) AS videos,
    sum(duration) AS duration,
    sum(score) AS score,
    sum(view_count) AS view_count,
    sum(like_count) AS like_count,
    sum(comment_count) AS comment_count,
    sum(is_clickbait) AS clickbait_count
   FROM public.video_stat_change vs
  GROUP BY category_id, report_period, channel_id, published_period, is_new, is_short
 HAVING (count(*) > 0);

--
-- Name: channel_period_top; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.channel_period_top AS
 WITH total_metrics AS (
         SELECT vs.category_id,
            vs.report_period,
            vs.channel_id,
            sum(vs.score) AS score,
            sum(((vs.videos * vs.is_new) * (1 - vs.is_short))) AS videos,
            sum(((vs.clickbait_count * vs.is_new) * (1 - vs.is_short))) AS video_clickbaits,
            sum(((vs.videos * vs.is_new) * vs.is_short)) AS shorts,
            sum((vs.duration * vs.is_new)) AS duration,
            sum(vs.view_count) AS view_count,
            sum(vs.like_count) AS like_count,
            sum(vs.comment_count) AS comment_count,
            sum(((vs.view_count * (vs.is_new)::numeric) * ((1 - vs.is_short))::numeric)) AS view_count_new_video,
            sum(((vs.view_count * (vs.is_new)::numeric) * (vs.is_short)::numeric)) AS view_count_new_short,
            sum(((vs.view_count * ((1 - vs.is_new))::numeric) * ((1 - vs.is_short))::numeric)) AS view_count_old_video,
            sum(((vs.view_count * ((1 - vs.is_new))::numeric) * (vs.is_short)::numeric)) AS view_count_old_short
           FROM public.video_stat_subgroup vs
          GROUP BY vs.category_id, vs.report_period, vs.channel_id
        ), ranked AS (
         SELECT total_metrics.category_id,
            total_metrics.report_period,
            total_metrics.channel_id,
            total_metrics.score,
            total_metrics.videos,
            total_metrics.video_clickbaits,
            total_metrics.shorts,
            total_metrics.duration,
            total_metrics.view_count,
            total_metrics.like_count,
            total_metrics.comment_count,
            total_metrics.view_count_new_video,
            total_metrics.view_count_new_short,
            total_metrics.view_count_old_video,
            total_metrics.view_count_old_short,
            row_number() OVER (PARTITION BY total_metrics.report_period, total_metrics.category_id ORDER BY total_metrics.score DESC) AS rank
           FROM total_metrics
        )
 SELECT category_id,
    report_period,
    channel_id,
    score,
    videos,
    video_clickbaits,
    shorts,
    duration,
    view_count,
    like_count,
    comment_count,
    view_count_new_video,
    view_count_new_short,
    view_count_old_video,
    view_count_old_short,
    rank
   FROM ranked;

--
-- Name: channel_period_top_change; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.channel_period_top_change AS
 SELECT cur.category_id,
    cur.report_period,
    cur.channel_id,
    cur.score,
    cur.videos,
    cur.video_clickbaits,
    cur.shorts,
    cur.duration,
    cur.view_count,
    cur.like_count,
    cur.comment_count,
    cur.view_count_new_video,
    cur.view_count_new_short,
    cur.view_count_old_video,
    cur.view_count_old_short,
    cur.rank,
        CASE
            WHEN (prev.channel_id IS NULL) THEN (0)::numeric
            ELSE (cur.score - prev.score)
        END AS score_change,
        CASE
            WHEN (prev.channel_id IS NULL) THEN (0)::bigint
            ELSE (- (cur.rank - prev.rank))
        END AS rank_change
   FROM (public.channel_period_top cur
     LEFT JOIN public.channel_period_top prev ON ((((prev.channel_id)::text = (cur.channel_id)::text) AND (prev.report_period = (cur.report_period - '1 mon'::interval)))));

--
-- Name: channel_period_top_videos; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.channel_period_top_videos AS
 WITH ranked AS (
         SELECT video_stat_change.category_id,
            video_stat_change.report_period,
            video_stat_change.published_period,
            video_stat_change.channel_id,
            video_stat_change.video_id,
            video_stat_change.is_clickbait,
            video_stat_change.is_new,
            video_stat_change.is_short,
            video_stat_change.duration,
            video_stat_change.cur_vs_id,
            video_stat_change.prev_vs_id,
            video_stat_change.score,
            video_stat_change.view_count,
            video_stat_change.like_count,
            video_stat_change.comment_count,
            video_stat_change.cur_view_count,
            video_stat_change.prev_view_count,
            video_stat_change.cur_like_count,
            video_stat_change.prev_like_count,
            video_stat_change.cur_comment_count,
            video_stat_change.prev_comment_count,
            row_number() OVER (PARTITION BY video_stat_change.report_period, video_stat_change.channel_id ORDER BY video_stat_change.is_short, video_stat_change.score DESC) AS rank
           FROM public.video_stat_change
          WHERE (video_stat_change.is_new = 1)
        )
 SELECT r.category_id,
    r.report_period,
    r.published_period,
    r.channel_id,
    r.video_id,
    r.is_clickbait,
    r.is_new,
    r.is_short,
    r.duration,
    r.cur_vs_id,
    r.prev_vs_id,
    r.score,
    r.view_count,
    r.like_count,
    r.comment_count,
    r.cur_view_count,
    r.prev_view_count,
    r.cur_like_count,
    r.prev_like_count,
    r.cur_comment_count,
    r.prev_comment_count,
    r.rank,
    v.title,
    v.video_url,
    v.thumbnail_url,
    v.clickbait_comment
   FROM (ranked r
     LEFT JOIN public.video v ON (((v.video_id)::text = (r.video_id)::text)));

--
-- Name: channel_stat; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channel_stat (
    channel_id character varying NOT NULL,
    data_at timestamp without time zone NOT NULL,
    report_period date,
    channel_view_count bigint,
    subscriber_count bigint,
    video_count integer,
    id integer NOT NULL,
    pc_view bigint,
    pc_subscriber bigint,
    pc_video bigint,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    ppcs_id integer
);

--
-- Name: channel_rating; Type: TABLE; Schema: public; Owner: -
-- Materialized monthly rating (API product): channel + channel_stat + video agg.

CREATE TABLE public.channel_rating (
    id integer NOT NULL,
    channel_id character varying NOT NULL,
    report_period date NOT NULL,
    channel_title text,
    description text,
    custom_url text,
    thumbnail_url text,
    category_id integer,
    stats_at timestamp without time zone,
    channel_views bigint,
    channel_subscribers bigint,
    channel_videos integer,
    channel_views_mom bigint,
    channel_subscribers_mom bigint,
    channel_videos_mom integer,
    new_longs integer,
    new_shorts integer,
    duration_sec bigint,
    video_views bigint,
    views_new_long bigint,
    views_new_short bigint,
    views_old_long bigint,
    views_old_short bigint,
    video_likes bigint,
    video_comments bigint,
    score bigint,
    score_mom bigint,
    rank integer,
    rank_mom integer,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    _created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    _updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

--
-- Name: channel_stat_change; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.channel_stat_change AS
 SELECT cur.report_period,
    c.channel_id,
    c.channel_title,
    cur.channel_view_count,
    cur.video_count,
    cur.subscriber_count,
        CASE
            WHEN (pr.id IS NULL) THEN NULL::bigint
            ELSE (cur.channel_view_count - pr.channel_view_count)
        END AS total_view_count_change,
        CASE
            WHEN (pr.id IS NULL) THEN NULL::integer
            ELSE (cur.video_count - pr.video_count)
        END AS total_video_change,
        CASE
            WHEN (pr.id IS NULL) THEN NULL::bigint
            ELSE (cur.subscriber_count - pr.subscriber_count)
        END AS subscriber_count_change
   FROM ((public.channel c
     LEFT JOIN public.channel_stat cur ON (((cur.channel_id)::text = (c.channel_id)::text)))
     LEFT JOIN public.channel_stat pr ON ((((pr.channel_id)::text = (c.channel_id)::text) AND (pr.report_period = (cur.report_period - '1 mon'::interval)))))
  WHERE (c.status > 0)
  ORDER BY cur.report_period;

--
-- Name: channel_stat_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.channel_stat_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: channel_stat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.channel_stat_id_seq OWNED BY public.channel_stat.id;

--
-- Name: channel_rating_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.channel_rating_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.channel_rating_id_seq OWNED BY public.channel_rating.id;

--
-- Name: channel_v; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.channel_v AS
 SELECT ch.category_id,
    ch.channel_id,
    ch.channel_title,
    ch.description,
    ch.published_at,
    ch.thumbnail_url,
    ch.custom_url,
    ch.status,
    ch.id,
    ch.last_video_fetch_dt,
    ch.created_at,
    ch.updated_at,
    ch.data,
    c.active AS category_status,
    c.sys_name,
    c.name AS category_name,
    c.title AS category_title,
    c.description AS category_description
   FROM (public.channel ch
     LEFT JOIN public.category c ON ((c.id = ch.category_id)));

--
-- Name: pipeline_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_run (
    scenario text NOT NULL,
    period date NOT NULL,
    step_id text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id bigint NOT NULL,
    step_ord integer
);

--
-- Name: pipeline_run_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: pipeline_run_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_run_id_seq OWNED BY public.pipeline_run.id;

--
-- Name: playlist_shorts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.playlist_shorts (
    id integer NOT NULL,
    video_id text NOT NULL,
    channel_id text NOT NULL,
    title text,
    published_at timestamp without time zone NOT NULL,
    published_at_period date,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

--
-- Name: playlist_shorts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.playlist_shorts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: playlist_shorts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.playlist_shorts_id_seq OWNED BY public.playlist_shorts.id;

--
-- Name: report; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report (
    report_period date NOT NULL,
    category_id integer NOT NULL,
    data jsonb NOT NULL,
    id integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: report_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.report_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: report_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.report_id_seq OWNED BY public.report.id;

--
-- Name: report_view; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.report_view AS
 SELECT c.category_id,
    c.report_period,
    c.channel_id,
    c.score,
    c.videos,
    c.video_clickbaits,
    c.shorts,
    c.duration,
    c.view_count,
    c.like_count,
    c.comment_count,
    c.view_count_new_video,
    c.view_count_new_short,
    c.view_count_old_video,
    c.view_count_old_short,
    c.rank,
    c.score_change,
    c.rank_change,
    ch.channel_title,
    ch.thumbnail_url,
    ch.custom_url,
    ch.description,
    cs.subscriber_count,
    cs.subscriber_count_change,
    cs.total_video_change,
    cs.total_view_count_change,
    ((cs.total_view_count_change)::numeric - c.view_count) AS view_count_check
   FROM ((public.channel ch
     LEFT JOIN public.channel_stat_change cs ON (((ch.channel_id)::text = (cs.channel_id)::text)))
     LEFT JOIN public.channel_period_top_change c ON ((((ch.channel_id)::text = (c.channel_id)::text) AND (c.report_period = cs.report_period))))
  ORDER BY c.report_period, c.category_id, c.rank;

--
-- Name: video_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.video_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: video_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.video_id_seq OWNED BY public.video.id;

--
-- Name: video_stat_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.video_stat_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: video_stat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.video_stat_id_seq OWNED BY public.video_stat.id;

--
-- Name: wordstat; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wordstat (
    id integer NOT NULL,
    category_id integer NOT NULL,
    period date NOT NULL,
    lexeme text NOT NULL,
    word text NOT NULL,
    freq integer NOT NULL,
    type smallint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

--
-- Name: wordstat_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wordstat_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: wordstat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wordstat_id_seq OWNED BY public.wordstat.id;

--
-- Name: category id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category ALTER COLUMN id SET DEFAULT nextval('public.category_id_seq'::regclass);

--
-- Name: channel id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel ALTER COLUMN id SET DEFAULT nextval('public.channel_id_seq'::regclass);

--
-- Name: channel_stat id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_stat ALTER COLUMN id SET DEFAULT nextval('public.channel_stat_id_seq'::regclass);


ALTER TABLE ONLY public.channel_rating ALTER COLUMN id SET DEFAULT nextval('public.channel_rating_id_seq'::regclass);

--
-- Name: pipeline_run id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_run ALTER COLUMN id SET DEFAULT nextval('public.pipeline_run_id_seq'::regclass);

--
-- Name: playlist_shorts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.playlist_shorts ALTER COLUMN id SET DEFAULT nextval('public.playlist_shorts_id_seq'::regclass);

--
-- Name: report id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report ALTER COLUMN id SET DEFAULT nextval('public.report_id_seq'::regclass);

--
-- Name: video id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video ALTER COLUMN id SET DEFAULT nextval('public.video_id_seq'::regclass);

--
-- Name: video_stat id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video_stat ALTER COLUMN id SET DEFAULT nextval('public.video_stat_id_seq'::regclass);

--
-- Name: wordstat id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordstat ALTER COLUMN id SET DEFAULT nextval('public.wordstat_id_seq'::regclass);

--
-- Name: category category_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category
    ADD CONSTRAINT category_pkey PRIMARY KEY (id);

--
-- Name: channel channel_channel_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT channel_channel_id_key UNIQUE (channel_id);

--
-- Name: channel channel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT channel_pkey PRIMARY KEY (id);

--
-- Name: channel_stat channel_stat_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_stat
    ADD CONSTRAINT channel_stat_pkey PRIMARY KEY (id);


ALTER TABLE ONLY public.channel_rating
    ADD CONSTRAINT channel_rating_pkey PRIMARY KEY (id);


ALTER TABLE ONLY public.channel_rating
    ADD CONSTRAINT uq_channel_rating UNIQUE (channel_id, report_period);

--
-- Name: pipeline_run pipeline_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_run
    ADD CONSTRAINT pipeline_run_pkey PRIMARY KEY (scenario, period, step_id);

--
-- Name: playlist_shorts playlist_shorts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.playlist_shorts
    ADD CONSTRAINT playlist_shorts_pkey PRIMARY KEY (id);

--
-- Name: playlist_shorts playlist_shorts_video_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.playlist_shorts
    ADD CONSTRAINT playlist_shorts_video_id_key UNIQUE (video_id);

--
-- Name: report report_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report
    ADD CONSTRAINT report_pkey PRIMARY KEY (id);

--
-- Name: report uq_period_category; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report
    ADD CONSTRAINT uq_period_category UNIQUE (report_period, category_id);

--
-- Name: wordstat uq_wordstat_cat_period_lexeme; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordstat
    ADD CONSTRAINT uq_wordstat_cat_period_lexeme UNIQUE (category_id, period, lexeme);

--
-- Name: video video_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video
    ADD CONSTRAINT video_pkey PRIMARY KEY (id);

--
-- Name: video_stat video_stat_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video_stat
    ADD CONSTRAINT video_stat_pkey PRIMARY KEY (id);

--
-- Name: video video_video_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video
    ADD CONSTRAINT video_video_id_key UNIQUE (video_id);

--
-- Name: wordstat wordstat_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wordstat
    ADD CONSTRAINT wordstat_pkey PRIMARY KEY (id);

--
-- Name: idx_channel_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_channel_category_id ON public.channel USING btree (category_id);

--
-- Name: idx_channel_last_shorts_fetch_dt; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_channel_last_shorts_fetch_dt ON public.channel USING btree (last_shorts_fetch_dt);

--
-- Name: idx_channel_last_video_fetch_dt; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_channel_last_video_fetch_dt ON public.channel USING btree (last_video_fetch_dt);

--
-- Name: idx_channel_stat_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_channel_stat_channel_id ON public.channel_stat USING btree (channel_id);

--
-- Name: idx_channel_stat_report_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_channel_stat_report_period ON public.channel_stat USING btree (report_period);

CREATE INDEX idx_channel_rating_report_period ON public.channel_rating USING btree (report_period);

CREATE INDEX idx_channel_rating_cat_period_rank ON public.channel_rating USING btree (category_id, report_period, rank);

--
-- Name: idx_playlist_shorts_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_playlist_shorts_channel_id ON public.playlist_shorts USING btree (channel_id);

--
-- Name: idx_playlist_shorts_channel_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_playlist_shorts_channel_published ON public.playlist_shorts USING btree (channel_id, published_at);

--
-- Name: idx_playlist_shorts_published_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_playlist_shorts_published_period ON public.playlist_shorts USING btree (published_at_period);

--
-- Name: idx_playlist_shorts_video_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_playlist_shorts_video_id ON public.playlist_shorts USING btree (video_id);

--
-- Name: idx_video_aggregate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_aggregate ON public.video USING btree (published_at_period, channel_id, rank);

--
-- Name: idx_video_is_short_null; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_is_short_null ON public.video USING btree (video_id) WHERE ((is_short IS NULL) AND (status = 1));

--
-- Name: idx_video_published_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_published_period ON public.video USING btree (published_at_period);

--
-- Name: idx_video_rank_top10; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_rank_top10 ON public.video USING btree (rank) WHERE (rank <= 10);

--
-- Name: idx_video_rank_video_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_rank_video_id ON public.video USING btree (rank, video_id);

--
-- Name: idx_video_stat_aggregate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_stat_aggregate ON public.video_stat USING btree (report_period, channel_id, is_new, is_short);

--
-- Name: idx_video_stat_report_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_stat_report_period ON public.video_stat USING btree (report_period);

--
-- Name: idx_video_stat_video_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_stat_video_id ON public.video_stat USING btree (video_id);

--
-- Name: idx_video_title_tsv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_title_tsv ON public.video USING gin (title_tsv);

--
-- Name: idx_video_wo_duration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_wo_duration ON public.video USING btree (video_id) WHERE ((status = 1) AND (duration IS NULL));

--
-- Name: idx_wordstat_cat_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wordstat_cat_period ON public.wordstat USING btree (category_id, period);

--
-- Name: idx_wordstat_cat_period_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wordstat_cat_period_type ON public.wordstat USING btree (category_id, period, type);

--
-- Name: video trg_video_title_tsv; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_video_title_tsv BEFORE INSERT OR UPDATE OF title ON public.video FOR EACH ROW EXECUTE FUNCTION public.video_title_tsv_update();

--
-- Name: channel trigger_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at BEFORE UPDATE ON public.channel FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: channel_stat trigger_set_updated_at_channel; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_channel BEFORE UPDATE ON public.channel_stat FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


CREATE TRIGGER trg_channel_stat_set_pc
    BEFORE INSERT OR UPDATE OF channel_view_count, subscriber_count, video_count, report_period
    ON public.channel_stat
    FOR EACH ROW
    EXECUTE FUNCTION public.channel_stat_set_pc();


CREATE FUNCTION public.channel_rating_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW._updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_channel_rating_set_updated_at
    BEFORE UPDATE ON public.channel_rating
    FOR EACH ROW
    EXECUTE FUNCTION public.channel_rating_set_updated_at();

--
-- Name: playlist_shorts trigger_set_updated_at_playlist_shorts; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_playlist_shorts BEFORE UPDATE ON public.playlist_shorts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: report trigger_set_updated_at_report; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_report BEFORE UPDATE ON public.report FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: video trigger_set_updated_at_video; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_video BEFORE UPDATE ON public.video FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: video_stat trigger_set_updated_at_video; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_video BEFORE UPDATE ON public.video_stat FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: wordstat trigger_set_updated_at_wordstat; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trigger_set_updated_at_wordstat BEFORE UPDATE ON public.wordstat FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: channel_stat channel_stat_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_stat
    ADD CONSTRAINT channel_stat_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channel(channel_id);


ALTER TABLE ONLY public.channel_rating
    ADD CONSTRAINT channel_rating_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channel(channel_id);

--
-- Name: playlist_shorts playlist_shorts_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.playlist_shorts
    ADD CONSTRAINT playlist_shorts_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channel(channel_id);

--
-- Name: report report_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report
    ADD CONSTRAINT report_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.category(id);

--
-- Name: video video_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video
    ADD CONSTRAINT video_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channel(channel_id);

--
-- Name: video_stat video_stat_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video_stat
    ADD CONSTRAINT video_stat_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.video(video_id);

--
-- PostgreSQL database dump complete
--
