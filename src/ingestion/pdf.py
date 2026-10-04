import hashlib
import json
import logging
import re
import shutil
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from sqlalchemy import insert, select

from ..chunking import semantic_chunks
from ..db import chunks, sources
from ..models import now


def ingest_pdf(store, path, title='كتاب وليد', author='', profile='standard', data_dir='data', actual_title='', ocr_pages=None):
    """Explicit profiles avoid silently guessing Arabic reading order.

    rtl_visual: reverse glyph-order lines from pdfplumber, retaining raw text.
    ocr_pages: page-number -> externally produced OCR text; always unverified.
    """
    path = Path(path)
    if path.stat().st_size > 50 * 1024 * 1024: raise ValueError('PDF exceeds 50 MB (the private storage bucket limit)')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    source_id = f'SRC-{sha[:16]}'
    with store.engine.connect() as c:
        existing = c.execute(select(sources.c.payload).where(sources.c.sha256 == sha)).scalar_one_or_none()
    if existing: return existing
    if profile not in ('standard', 'rtl_visual'): raise ValueError('Unknown extraction profile')
    pages = []
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    if profile == 'rtl_visual':
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > 2000: raise ValueError('Too many PDF pages')
            for i, page in enumerate(pdf.pages, 1):
                raw = page.extract_text(char_dir='rtl', line_dir='ttb') or ''
                pages.append({'page_number': i, 'raw_text': raw, 'text': '\n'.join(line[::-1] for line in raw.splitlines()), 'extraction_method': 'pdfplumber:rtl_visual:reverse_lines', 'quality_status': 'needs_visual_review'})
    else:
        reader = PdfReader(path)
        if len(reader.pages) > 2000: raise ValueError('Too many PDF pages')
        for i, page in enumerate(reader.pages, 1):
            raw = page.extract_text() or ''
            pages.append({'page_number': i, 'raw_text': raw, 'text': raw, 'extraction_method': 'pypdf:standard', 'quality_status': 'needs_visual_review'})
    for p in pages:
        if ocr_pages and str(p['page_number']) in ocr_pages:
            p.update(text=ocr_pages[str(p['page_number'])], extraction_method='external_ocr', quality_status='needs_visual_review')
        if len(re.findall(r'[\u0621-\u064a]', p['text'])) < 20:
            p['quality_status'] = 'needs_ocr_or_nontext_page_review'
    folder = Path(data_dir) / 'source' / source_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'original.pdf'
    shutil.copyfile(path, target)
    source = {'id': source_id, 'source_type': 'book', 'source_name': title, 'actual_title': actual_title, 'author': author, 'sha256': sha, 'pdf_path': str(target.resolve()), 'page_count': len(pages), 'created_at': now(), 'extraction_profile': profile, 'rights_status': 'private_user_supplied_not_for_redistribution', 'review_status': 'needs_review', 'metadata_status': 'operator_supplied', 'page_number_type': 'pdf_1_based'}
    (folder / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
    section = ''
    with store.transaction() as c:
        # Recheck inside the serialized transaction for concurrent identical uploads.
        existing = c.execute(select(sources.c.payload).where(sources.c.sha256 == sha)).scalar_one_or_none()
        if existing: return existing
        c.execute(insert(sources).values(id=source_id, sha256=sha, payload=source))
        for p in pages:
            for part, (start, end, txt) in enumerate(semantic_chunks(p['text']), 1):
                heads = re.findall(r'(?m)^(?:الفرع|الفصل|الباب)\s+[^:\n]{1,70}\s*[:：]', txt)
                if heads: section = heads[-1].strip()
                cid = f"{source_id}-P{p['page_number']:04d}-C{part:03d}"
                c.execute(insert(chunks).values(id=cid, source_id=source_id, page_number=p['page_number'], section=section, text=txt, raw_text=p['raw_text'], payload={'page_start': start, 'page_end': end, 'extraction_method': p['extraction_method'], 'quality_status': p['quality_status']}))
    return source
