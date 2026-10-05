import random

from ..db import digest
from ..models import now
from ..parsing import normalize_arabic

METRICS = ['primary_pattern_accuracy', 'sub_pattern_accuracy', 'central_claim_accuracy', 'objection_decomposition_accuracy', 'source_grounding_accuracy', 'citation_accuracy', 'unsupported_diagnosis_rate', 'human_review_trigger_accuracy', 'duplicate_family_detection_accuracy']


def connected_groups(records, duplicate_runs=None):
    parent = {r['id']: r['id'] for r in records}
    def root(x):
        if parent[x] != x: parent[x] = root(parent[x])
        return parent[x]
    def union(a, b):
        if a in parent and b in parent: parent[root(a)] = root(b)
    seen = {}
    for r in records:
        keys = [('wording', normalize_arabic(r['objection_text_ar']))]
        keys += [(k, r[k]) for k in ('family_id', 'duplicate_group_id') if r[k]]
        for key in keys:
            if key in seen: union(r['id'], seen[key])
            seen[key] = r['id']
    for run in duplicate_runs or []:
        for pair in run['payload'].get('pairs', []):
            if pair['similarity_type'] in ('exact_duplicate', 'paraphrase', 'same_underlying_objection'): union(pair['a'], pair['b'])
    groups = {}
    for r in records: groups.setdefault(root(r['id']), []).append(r['id'])
    return list(groups.values())


def leakage_groups(store, conn=None):
    """Include withdrawn records and historical links: withdrawal must not erase a holdout."""
    runs = list(store.list_documents('duplicate_runs', conn))
    groups = [f['examples'] for f in store.records('family', conn=conn)]
    groups += [g for m in store.list_documents('dataset_manifests', conn) for g in m['payload']['groups']]
    for group in groups:
        if group: runs.append({'payload': {'pairs': [{'a': group[0], 'b': rid, 'similarity_type': 'same_underlying_objection'} for rid in group[1:]]}})
    return connected_groups(store.records('objection', conn=conn), runs)


def create_benchmark(store, test_ids=None, validation_ids=None, auto=False, seed=42, reviewer_id='operator'):
    with store.transaction() as c:
        records = store.eligible('objection', c)
        ids = {r['id'] for r in records}
        all_groups = leakage_groups(store, c)
        groups = [sorted(set(g) & ids) for g in all_groups if set(g) & ids]
        test, val = set(test_ids or []), set(validation_ids or [])
        if auto:
            if test or val: raise ValueError('Choose automatic splitting or explicit holdout IDs, not both')
            if len(records) < 100 or len(groups) < 20: raise ValueError('Small dataset: select manual benchmark IDs; auto split needs >=100 records and >=20 independent groups')
            random.Random(seed).shuffle(groups)
            for group in groups:
                if len(test) < len(records)*.15: test.update(group)
                elif len(val) < len(records)*.15: val.update(group)
        else:
            if not test: raise ValueError('Select approved manual benchmark cases')
            if (test | val) - ids: raise ValueError('Only eligible approved cases may enter a benchmark')
            for group in groups:
                if test.intersection(group) and val.intersection(group): raise ValueError('Family spans test and validation')
                if test.intersection(group): test.update(group)
                elif val.intersection(group): val.update(group)
        # Any previously exported training content is permanently ineligible as a held-out test.
        exported = {x['id'] for e in store.list_documents('training_exports', c) for x in e['payload']['records']}
        if (test | val) & exported: raise ValueError('Benchmark contamination: case already exported for training')
        for group in all_groups:
            if (test | val).intersection(group) and exported.intersection(group): raise ValueError('Benchmark family already used for training')
        # Previously reserved evaluation examples are never returned to training.
        reserved = {x for m in store.list_documents('dataset_manifests', c) for k in ('test_ids', 'validation_ids') for x in m['payload'][k]}
        train = ids - test - val - reserved
        for group in all_groups:
            if reserved.intersection(group): train.difference_update(group)
        manifest = {'created_at': now(), 'created_by': reviewer_id, 'mode': 'grouped_70_15_15' if auto else 'manual_benchmark', 'seed': seed, 'training_ids': sorted(train), 'validation_ids': sorted(val), 'test_ids': sorted(test), 'groups': all_groups, 'records': [{'id': r['id'], 'version': r['version'], 'hash': digest(r), 'snapshot': r} for r in records], 'ratio_note': 'Ratios are approximate because families remain intact.'}
        mid = 'SPLIT-' + digest(manifest)[:16]
        store.save_document('dataset_manifests', manifest, mid, c)
        return {'id': mid, **manifest}


HUMAN_METRICS = ('central_claim_accuracy', 'objection_decomposition_accuracy', 'source_grounding_accuracy', 'citation_accuracy', 'unsupported_diagnosis_rate')


def evaluate_predictions(store, manifest_id, predictions, human_scores=None, split='test'):
    if split not in ('test', 'validation'): raise ValueError('Evaluate only a held-out split')
    manifests = {m['id']: m['payload'] for m in store.list_documents('dataset_manifests')}
    m = manifests[manifest_id]
    ids = m[split + '_ids']
    gold = {r['id']: r['snapshot'] for r in m['records']}
    if set(predictions) - set(ids): raise ValueError('Predictions contain cases outside benchmark')
    eligible = {r['id']: r for r in store.eligible('objection')}
    for rid in ids:
        if rid not in eligible or digest(eligible[rid]) != digest(gold[rid]): raise ValueError('Benchmark approval/version changed; create a new manifest')
    scores = {k: [] for k in METRICS}
    per_case = []
    for rid in ids:
        expected, pred = gold[rid], predictions.get(rid)
        if pred is None:
            per_case.append({'id': rid, 'status': 'missing_prediction'})
            scores['primary_pattern_accuracy'].append(0)
            scores['sub_pattern_accuracy'].append(0)
            scores['human_review_trigger_accuracy'].append(0)
            continue
        a = pred.get('analysis', pred) if isinstance(pred, dict) else None
        if not isinstance(a, dict) or not isinstance(a.get('sub_patterns', []), list) or not all(isinstance(x, str) for x in a.get('sub_patterns', [])):
            raise ValueError(f'Prediction for {rid} must be an analysis object with a list of sub-pattern names')
        scores['primary_pattern_accuracy'].append(int(a.get('primary_pattern') == expected['primary_pattern']))
        scores['sub_pattern_accuracy'].append(int(set(a.get('sub_patterns', [])) == set(expected['sub_patterns'])))
        required = expected['primary_pattern'] in ('unknown', 'mixed_pattern', 'multiple_claims', 'insufficient_evidence', 'requires_human_review')
        # Raw model trigger is scored before the production gate, which always requires review.
        scores['human_review_trigger_accuracy'].append(int(a.get('requires_human_review') == required))
        scores['duplicate_family_detection_accuracy'].append(int(a.get('family_id') == expected['family_id'])) if expected['family_id'] else None
        raw = (human_scores or {}).get(rid, {})
        hs = {k: raw[k] for k in HUMAN_METRICS if isinstance(raw, dict) and k in raw}  # nothing else is stored
        for metric in ('central_claim_accuracy', 'objection_decomposition_accuracy', 'source_grounding_accuracy', 'citation_accuracy', 'unsupported_diagnosis_rate'):
            item = hs.get(metric)
            if item is not None:
                if not isinstance(item, dict) or not item.get('reviewer_id') or item.get('score') not in (0, 1): raise ValueError('Human metrics require reviewer attribution and binary score')
                scores[metric].append(item['score'])
        per_case.append({'id': rid, 'status': 'scored', 'human_scores': hs})
    metrics = {k: {'value': sum(v)/len(v) if v else None, 'rated_count': len(v), 'total_cases': len(ids), 'status': 'measured' if v else 'not_measured'} for k,v in scores.items()}
    run = {'manifest_id': manifest_id, 'split': split, 'at': now(), 'metrics': metrics, 'per_case': per_case, 'predictions': predictions, 'coverage': len(set(predictions) & set(ids))/len(ids) if ids else 0}
    run['id'] = store.save_document('evaluation_runs', run)
    return run


def reviewer_agreement(labels_a, labels_b):
    common = set(labels_a) & set(labels_b)
    if not common: return {'n': 0, 'agreement': None, 'cohen_kappa': None}
    from collections import Counter
    a, b = Counter(labels_a[x] for x in common), Counter(labels_b[x] for x in common)
    n = len(common)
    po = sum(labels_a[x] == labels_b[x] for x in common)/n
    pe = sum(a[k]*b[k] for k in set(a)|set(b))/(n*n)
    return {'n': n, 'agreement': po, 'cohen_kappa': (po-pe)/(1-pe) if pe < 1 else None}
