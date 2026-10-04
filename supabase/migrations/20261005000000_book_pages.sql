-- 20261005000000: allow rendered page images (in-site book viewer) in the private sources bucket.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'storage' AND table_name = 'buckets') THEN
    UPDATE storage.buckets SET allowed_mime_types = ARRAY['application/pdf', 'image/webp'] WHERE id = 'sources';
  END IF;
END $$;
