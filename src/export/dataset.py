import hashlib
import json
from pathlib import Path

from ..db import digest
from ..evaluation.benchmark import leakage_groups
from ..models import Analysis, now


def build_training_export(store, manifest_id, conn=None, path=None):
    """Select and serialize approved, leak-free training cases; records the export in the database.

    Returns (content, result). No filesystem access, so it also runs on read-only hosts."""
    if conn is None:
        with store.transaction() as c: return build_training_export(store, manifest_id, c, path)
    c = conn
    manifests = {m['id']: m['payload'] for m in store.list_documents('dataset_manifests', c)}
    m = manifests[manifest_id]
    records = {r['id']: r for r in store.eligible('objection', c)}
    snapshots = {r['id']: r for r in m['records']}
    reserved = {x for v in manifests.values() for k in ('test_ids', 'validation_ids') for x in v[k]}
    groups = leakage_groups(store, c)
    changed = True
    while changed:
        old = len(reserved)
        for group in groups:
            if reserved.intersection(group): reserved.update(group)
        changed = old != len(reserved)
    chosen = []
    for rid in m['training_ids']:
        if rid in reserved: continue
        if rid not in records or digest(records[rid]) != snapshots[rid]['hash']: raise ValueError('Approval or record version changed; create a fresh split')
        chosen.append(records[rid])
    if not chosen: raise ValueError('No eligible training cases; no export produced')
    lines = []
    for r in chosen:
        assistant = {k: r[k] for k in Analysis.model_fields}
        lines.append(json.dumps({'messages': [{'role': 'system', 'content': 'حلل بنية الشبهة وفق منهج مَنْهَج. لا تقدم حكما شرعيا مستقلا.'}, {'role': 'user', 'content': r['objection_text_ar']}, {'role': 'assistant', 'content': json.dumps(assistant, ensure_ascii=False)}]}, ensure_ascii=False))
    content = '\n'.join(lines) + '\n'
    sha = hashlib.sha256(content.encode()).hexdigest()
    payload = {'manifest_id': manifest_id, 'at': now(), 'records': [{'id': r['id'], 'version': r['version'], 'hash': digest(r)} for r in chosen], 'content_sha256': sha, 'path': str(Path(path).resolve()) if path else None, 'delivery': 'file' if path else 'download'}
    eid = store.save_document('training_exports', payload, conn=c)
    return content, {'export_id': eid, 'count': len(chosen), 'sha256': sha}


def export_training(store, manifest_id, output_path):
    with store.transaction() as c:
        content, result = build_training_export(store, manifest_id, c, output_path)
        # Atomic replacement; DB transaction records exactly which rows were selected.
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(path)
        return {**result, 'path': str(path)}


def export_snapshots(store, data_dir='data'):
    root = Path(data_dir)
    for name in ('pending_review', 'approved', 'reviewed', 'rejected'):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        # Generated snapshots only; canonical database history remains append-only.
        for path in folder.glob('*.json'): path.unlink()
    for r in store.records():
        name = {'draft': 'pending_review', 'needs_review': 'pending_review', 'approved': 'approved', 'rejected': 'rejected'}[r['review_status']]
        data = json.dumps(r, ensure_ascii=False, indent=2)
        (root / name / f"{r['id']}.json").write_text(data, encoding='utf-8')
        if r['human_review']: (root / 'reviewed' / f"{r['id']}.json").write_text(data, encoding='utf-8')
    return len(store.records())
