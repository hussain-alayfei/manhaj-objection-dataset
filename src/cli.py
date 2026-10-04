import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .db import Store
from .ingestion import ingest_pdf
from .parsing.extraction import extract_source
from .duplicate_detection import detect_duplicates
from .family_detection import create_families
from .retrieval import build_embeddings
from .retrieval.hybrid import SemanticEncoder
from .evaluation import create_benchmark, evaluate_predictions
from .export import export_training, export_snapshots
from .research import research_common_objections


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description='مَنْهَج: source-first dataset workbench')
    p.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db')
    ingest = sub.add_parser('ingest')
    ingest.add_argument('pdf'); ingest.add_argument('--title', default='كتاب وليد'); ingest.add_argument('--author', default='')
    ingest.add_argument('--actual-title', default=''); ingest.add_argument('--profile', choices=['standard', 'rtl_visual'], default='standard')
    ingest.add_argument('--ocr-pages', help='JSON map of PDF page numbers to OCR text; remains unverified')
    ext = sub.add_parser('extract'); ext.add_argument('source_id'); ext.add_argument('--kind', choices=['all','rule','objection'], default='all'); ext.add_argument('--model', action='store_true')
    emb = sub.add_parser('embeddings'); emb.add_argument('--include-drafts', action='store_true', help='also index unreviewed candidates for draft-mode diagnosis')
    sub.add_parser('duplicates'); sub.add_parser('families'); sub.add_parser('snapshots')
    bench = sub.add_parser('benchmark'); bench.add_argument('--test-ids', nargs='*', default=[]); bench.add_argument('--validation-ids', nargs='*', default=[]); bench.add_argument('--auto', action='store_true')
    export = sub.add_parser('export'); export.add_argument('manifest_id'); export.add_argument('--output', default='data/exports/training.jsonl')
    evaluate = sub.add_parser('evaluate'); evaluate.add_argument('manifest_id'); evaluate.add_argument('predictions'); evaluate.add_argument('--human-scores')
    research = sub.add_parser('research'); research.add_argument('topic'); research.add_argument('--limit', type=int, default=5)
    args = p.parse_args(); store = Store(args.database_url)
    if args.command == 'init-db': result = {'status': 'initialized'}
    elif args.command == 'ingest': result = ingest_pdf(store, args.pdf, args.title, args.author, args.profile, actual_title=args.actual_title, ocr_pages=json.loads(Path(args.ocr_pages).read_text(encoding='utf-8')) if args.ocr_pages else None)
    elif args.command == 'extract':
        if args.model:
            from .parsing.model_extraction import extract_with_model
            result = extract_with_model(store, args.source_id, kind=args.kind)
            export_snapshots(store)
        else: result = extract_source(store, args.source_id, args.kind)
        result = {k:v for k,v in result.items() if k not in ('inventory','candidate_ids')}
    elif args.command == 'embeddings': result = {'embedded_fields': build_embeddings(store, include_drafts=args.include_drafts)}
    elif args.command == 'duplicates':
        run = detect_duplicates(store, SemanticEncoder() if os.getenv('EMBEDDING_MODEL') else None)
        result = {'id': run['id'], 'mode': run['mode'], 'pairs': len(run['pairs'])}
    elif args.command == 'families':
        runs = store.list_documents('duplicate_runs')
        if not runs: raise ValueError('Run duplicates first')
        latest = max(runs, key=lambda d: d['payload'].get('at', ''))
        run = latest['payload']; run['id'] = latest['id']
        result = {'created': create_families(store, run)}
    elif args.command == 'benchmark': result = create_benchmark(store, args.test_ids, args.validation_ids, args.auto)
    elif args.command == 'export': result = export_training(store, args.manifest_id, args.output)
    elif args.command == 'snapshots': result = {'records': export_snapshots(store)}
    elif args.command == 'evaluate': result = evaluate_predictions(store, args.manifest_id, json.loads(Path(args.predictions).read_text(encoding='utf-8')), json.loads(Path(args.human_scores).read_text(encoding='utf-8')) if args.human_scores else None)
    elif args.command == 'research': result = research_common_objections(args.topic, args.limit, store)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
