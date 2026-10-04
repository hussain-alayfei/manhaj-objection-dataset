"""Upload an ingested source's original PDF to private Supabase Storage.

Usage: python scripts/upload_source_pdf.py SRC-<id> [--pdf path/to/original.pdf] [--upsert]
Verifies the file's SHA-256 against the source record before uploading.
"""
import argparse
import hashlib
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()
from sqlalchemy import select  # noqa: E402

from src.db import Store, sources  # noqa: E402
from src.storage import SupabaseStorage  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument('source_id')
p.add_argument('--pdf', help='defaults to data/source/<id>/original.pdf')
p.add_argument('--upsert', action='store_true')
args = p.parse_args()
pdf = Path(args.pdf or Path('data/source') / args.source_id / 'original.pdf')
data = pdf.read_bytes()
with Store().engine.connect() as c:
    source = c.execute(select(sources.c.payload).where(sources.c.id == args.source_id)).scalar_one_or_none()
if source is None: raise SystemExit(f'Unknown source {args.source_id}; seed the database first')
if hashlib.sha256(data).hexdigest() != source['sha256']: raise SystemExit('PDF does not match the ingested source (SHA-256 differs)')
key = SupabaseStorage().upload(args.source_id, data, upsert=args.upsert)
print(f'Uploaded {len(data):,} bytes to storage key {key}')
