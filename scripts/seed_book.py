"""Reproducible private source-derived seed. No fabricated or pre-approved records."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import Store
from src.ingestion import ingest_pdf
from src.parsing.extraction import extract_source
from src.export import export_snapshots
from dotenv import load_dotenv

load_dotenv()
if len(sys.argv) != 2: raise SystemExit('Usage: python scripts/seed_book.py PATH_TO_15110.pdf')
store = Store()
source = ingest_pdf(store, sys.argv[1], 'كتاب وليد', 'وليد بن راشد السعيدان', 'rtl_visual', actual_title='تربية الملكة على رد الشبهة')
run = extract_source(store, source['id'])
import runpy
runpy.run_path(str(Path(__file__).parent/'link_candidate_rules.py'), run_name='__main__')
runpy.run_path(str(Path(__file__).parent/'seed_structured_proposals.py'), run_name='__main__')
export_snapshots(store)
print({'source_id': source['id'], 'pages': source['page_count'], 'chunks': run['chunks_scanned'], 'headings': run['detected_headings'], 'new_records': run['new_records'], 'approved': 0})
