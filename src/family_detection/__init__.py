from ..db import digest
from ..models import Record


def create_families(store, duplicate_run):
    groups = {}
    for rid, suggestion in duplicate_run['suggestions'].items():
        key = suggestion['duplicate_group_id'] or rid
        groups.setdefault(key, []).append(store.get(rid))
    ids = []
    for key, records in groups.items():
        fid = 'FAM-' + digest([key, sorted(r['id'] for r in records)])[:12]
        first = records[0]
        r = Record(id=fid, kind='family', family_id=fid, title_ar='عائلة مرشحة: ' + first['title_ar'][:90], family_title_ar='عائلة مرشحة: ' + first['title_ar'][:90], core_claim_ar=first['central_claim_ar'], core_confusion_ar=first['diagnostic_reason_ar'], primary_pattern=first['primary_pattern'], common_variants_ar=[r['objection_text_ar'] for r in records], common_sub_patterns=sorted({p for r in records for p in r['sub_patterns']}), methodology_rules=sorted({p for r in records for p in r['methodology_rule_ids']}), examples=[r['id'] for r in records], ai_analysis={'engine': 'candidate_family_v1', 'duplicate_run_id': duplicate_run['id'], 'note_ar': 'الاشتراك في النمط وحده لا يكفي لدمج العائلات.'}).model_dump()
        if store.add(r): ids.append(fid)
    return ids
