-- Video title FTS: stored tsvector + trigger (russian).
-- Apply: psql $DATABASE_URL -f sql/video_title_tsv.sql
--    or: docker exec -i o2t4_db psql -U $USER -d $DB -f - < sql/video_title_tsv.sql

ALTER TABLE public.video
  ADD COLUMN IF NOT EXISTS title_tsv tsvector;

CREATE OR REPLACE FUNCTION video_title_tsv_update() RETURNS trigger AS $$
BEGIN
  NEW.title_tsv := to_tsvector('russian', coalesce(NEW.title, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_video_title_tsv ON video;
CREATE TRIGGER trg_video_title_tsv
  BEFORE INSERT OR UPDATE OF title ON video
  FOR EACH ROW
  EXECUTE FUNCTION video_title_tsv_update();

-- Backfill in batches (full-table UPDATE drops DataGrip / long sessions).
-- Re-run CALL if interrupted; only NULL rows are touched.
CREATE OR REPLACE PROCEDURE backfill_video_title_tsv(batch_size int DEFAULT 5000)
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

CALL backfill_video_title_tsv(5000);

select count(*) filter ( where  title_tsv is null) from video;
SELECT count(*)
FROM video
WHERE published_at_period = '2026-08-01'

  AND title_tsv IS NULL;

VACUUM (VERBOSE, PARALLEL 0) video;
SELECT n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relname='video';

-- After backfill (GIN on empty/partial is slower to maintain during UPDATE)
CREATE INDEX IF NOT EXISTS idx_video_title_tsv ON video USING GIN (title_tsv);
