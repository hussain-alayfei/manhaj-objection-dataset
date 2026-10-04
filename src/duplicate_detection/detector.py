import os
from difflib import SequenceMatcher
from itertools import combinations

from ..db import digest
from ..models import now
from ..parsing import normalize_arabic
from ..retrieval.hybrid import cosine


def thresholds():
    # Provisional cut-offs; recalibrate per embedding model on human-labelled Arabic pairs.
    return float(os.getenv('DUPLICATE_PARAPHRASE_THRESHOLD', '0.94')), float(os.getenv('DUPLICATE_SAME_OBJECTION_THRESHOLD', '0.84'))


def detect_duplicates(store, encoder=None):
    paraphrase, same_objection = thresholds()
    records = store.records('objection')
    vectors = encoder.encode([r['central_claim_ar'] or r['objection_text_ar'] for r in records]) if encoder and records else None
    pairs, parent = [], {r['id']: r['id'] for r in records}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, a), (j, b) in combinations(enumerate(records), 2):
        left, right = normalize_arabic(a['objection_text_ar']), normalize_arabic(b['objection_text_ar'])
        semantic = cosine(vectors[i], vectors[j]) if vectors else None
        if left and left == right: label = 'exact_duplicate'
        elif semantic is not None and semantic >= paraphrase: label = 'paraphrase'
        elif semantic is not None and semantic >= same_objection: label = 'same_underlying_objection'
        elif a['primary_pattern'] in ('جمع بين مختلفين', 'تفريق بين متماثلين') and a['primary_pattern'] == b['primary_pattern']:
            label = 'same_pattern_different_objection'
        else: label = 'new_case'
        if label in ('exact_duplicate', 'paraphrase', 'same_underlying_objection'):
            ra, rb = root(a['id']), root(b['id'])
            parent[max(ra, rb)] = min(ra, rb)
        if label != 'new_case':
            # Quadratic-cost lexical ratio only for pairs that are actually reported.
            lexical = SequenceMatcher(None, left, right, autojunk=False).ratio()
            pairs.append({'a': a['id'], 'b': b['id'], 'similarity_type': label, 'lexical_similarity': lexical, 'semantic_similarity': semantic, 'review_status': 'needs_review', 'method': 'embedding_threshold_proposal' if semantic is not None else 'exact_and_pattern_only'})
    groups = {}
    for r in records:
        key = root(r['id'])
        groups.setdefault(key, []).append(r['id'])
    suggestions = {}
    for ids in groups.values():
        gid = 'GRP-' + digest(sorted(ids))[:12] if len(ids) > 1 else None
        for rid in ids:
            links = [p for p in pairs if rid in (p['a'], p['b'])]
            strongest = next((k for k in ('exact_duplicate', 'paraphrase', 'same_underlying_objection', 'same_pattern_different_objection') if any(p['similarity_type'] == k for p in links)), 'new_case')
            suggestions[rid] = {'duplicate_group_id': gid, 'similarity_type': strongest, 'duplicate_candidates': links}
    run = {'at': now(), 'mode': 'semantic' if vectors else 'lexical_only_semantic_not_configured', 'model': encoder.model if encoder else None, 'suggestions': suggestions, 'pairs': pairs, 'note': 'Scores propose relationships; only a human review changes canonical annotations.'}
    run['id'] = store.save_document('duplicate_runs', run)
    return run
