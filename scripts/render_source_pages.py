"""Render every page of an ingested source PDF to WebP for the in-site book viewer.

Usage: python scripts/render_source_pages.py SRC-<id> [--pdf path/to/original.pdf] [--width 1100] [--local-only]

Pages are written to data/source/<id>/pages/0001.webp … (used by the local storage backend) and,
when STORAGE_BACKEND=supabase, uploaded to the private bucket at <id>/pages/0001.webp. The PDF's
SHA-256 must match the ingested source. Re-running replaces existing page images.
"""
import argparse
import hashlib
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()
import pypdfium2  # noqa: E402
from sqlalchemy import select  # noqa: E402

from src.db import Store, sources  # noqa: E402
from src.storage import SupabaseStorage, page_key  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument('source_id')
p.add_argument('--pdf')
p.add_argument('--width', type=int, default=1100)
p.add_argument('--local-only', action='store_true', help='do not upload to Supabase Storage')
args = p.parse_args()
pdf_path = Path(args.pdf or Path('data/source') / args.source_id / 'original.pdf')
data = pdf_path.read_bytes()
with Store().engine.connect() as c:
    source = c.execute(select(sources.c.payload).where(sources.c.id == args.source_id)).scalar_one_or_none()
if source is None: raise SystemExit(f'Unknown source {args.source_id}')
if hashlib.sha256(data).hexdigest() != source['sha256']: raise SystemExit('PDF does not match the ingested source (SHA-256 differs)')
remote = None if args.local_only or os.getenv('STORAGE_BACKEND', 'local') != 'supabase' else SupabaseStorage()
out_dir = Path('data/source') / args.source_id / 'pages'
out_dir.mkdir(parents=True, exist_ok=True)
document = pypdfium2.PdfDocument(data)
total_bytes = 0
for index in range(len(document)):
    page = document[index]
    scale = args.width / page.get_width()
    image = page.render(scale=scale).to_pil().convert('L')  # the book is black text on white: grayscale is smaller and sharper
    buffer = io.BytesIO()
    image.save(buffer, 'WEBP', quality=72, method=6)
    blob = buffer.getvalue()
    total_bytes += len(blob)
    (out_dir / f'{index + 1:04d}.webp').write_bytes(blob)
    if remote: remote.upload_object(page_key(args.source_id, index + 1), blob, 'image/webp', upsert=True)
    print(f'\rpage {index + 1}/{len(document)}', end='', flush=True)
print(f'\n{len(document)} pages, {total_bytes / 1024 / 1024:.1f} MB{" uploaded" if remote else " (local only)"}')
