"""Conservative extraction: exact spans first; candidate analysis never claims approval."""
import re
from pathlib import Path
import json

from ..db import digest
from ..models import Record, now
from . import normalize_arabic

HEAD = re.compile(r'(?m)^الفرع\s+[^:\n]{1,70}\s*:')
RULE = re.compile(r'القاعدة العامة|أن الشريعة لا تفرق|الاتفاق في الأسماء لا يستلزم|فليس كل شيء|كل ما كان مشروعا|فالوصف شيء زائد|دليل الأصل للأصل|دورك في الرد|وجه إزالتها|بيان الأصل الذي تقوم')


def corpus(store, source_id):
    source = next((s for s in store.source_list() if s['id'] == source_id), None)
    if source is None: raise KeyError(source_id)
    rows = store.source_chunks(source_id)
    text, mapping = '', []
    for i, row in enumerate(rows):
        if i and rows[i-1]['page_number'] != row['page_number']: text += '\n'
        start = len(text)
        text += row['text']
        mapping.append((start, len(text), row))
    text += '\n'
    return source, text, mapping


def citation(source, mapping, start, end, section=''):
    spans = []
    for a, b, row in mapping:
        lo, hi = max(start, a), min(end, b)
        if lo < hi:
            spans.append({'chunk_id': row['id'], 'page_number': row['page_number'], 'start': lo-a, 'end': hi-a, 'text': row['text'][lo-a:hi-a]})
    if not spans: raise ValueError('Empty evidence range')
    return {'source_id': source['id'], 'source_type': source['source_type'], 'source_name': source['source_name'], 'author': source.get('author', ''), 'page_number': spans[0]['page_number'], 'page_number_type': 'pdf_1_based' if source['source_type'] == 'book' else 'not_applicable', 'section': section, 'source_excerpt': '\n'.join(s['text'] for s in spans), 'spans': spans, 'source_url': source.get('source_url'), 'retrieved_at': source.get('retrieved_at'), 'source_date': source.get('source_date')}


def propose_pattern(text):
    n = normalize_arabic(text)
    a = bool(re.search(r'(الجمع|جمعوا|جمع|التسوية) بين (المختلف|مختلف)', n))
    b = bool(re.search(r'(التفريق|فرقوا|تفريق) بين (المتماثل|متماثل)', n))
    if a and b: return 'mixed_pattern'
    return 'جمع بين مختلفين' if a else 'تفريق بين متماثلين' if b else 'unknown'


def structure(pattern):
    if pattern == 'جمع بين مختلفين':
        return 'هل يوجد فارق مؤثر بين طرفي المقارنة؟', 'بيّن الفارق المؤثر'
    if pattern == 'تفريق بين متماثلين':
        return 'ما وجه التماثل، وهل يوجد فارق مؤثر يبرر اختلاف الحكم؟', 'بيّن وجه التماثل والجمع بينهما'
    return 'ما الدعوى المحددة، وما طرفا المقارنة ومعيارها؟', 'حرّر الدعوى والمقارنة قبل تحديد المعالجة'


def extract_source(store, source_id, kind='all', data_dir='data'):
    source, text, mapping = corpus(store, source_id)
    made, captured = [], []
    heads = list(HEAD.finditer(text))
    if kind in ('all', 'objection'):
        # Generic PDFs without branch headings enter a chunk-level candidate queue.
        ranges = [(m.start(), heads[i+1].start() if i+1 < len(heads) else len(text), m.group()) for i, m in enumerate(heads)]
        if not ranges: ranges = [(a, b, row['section']) for a, b, row in mapping]
        for start, end, heading in ranges:
            body_start = start + len(heading)
            body = text[body_start:end]
            stops = list(re.finditer(r'قلنا\s*:|فالجواب\s*:|الجواب\s*:|فنقول\s*:|فيكون دورك', body))
            stop = next((m.start() for m in stops if m.start() >= 50), min(len(body), 1100))
            # Full section stays in evidence; candidate wording is an exact extract.
            wording = body[:stop].strip()
            cit = citation(source, mapping, start, end, heading)
            pattern = propose_pattern(body)
            question, treatment = structure(pattern)
            rid = 'SHB-' + digest([source_id, start, end, 'extract-v1'])[:12]
            initial_claim = re.sub(r'\s+', ' ', wording)[:400]
            analysis = {'central_claim_ar': initial_claim, 'primary_pattern': pattern, 'diagnostic_reason_ar': 'ترشيح آلي من ألفاظ المقطع؛ تحرير الدعوى والتصنيف يحتاجان مراجعة بشرية.', 'revealing_question_ar': question, 'treatment_ar': treatment, 'response_path_ar': ['تحرير الدعوى من المقتطف', 'تحديد طرفي المقارنة ووجهها', 'فحص الفارق أو وجه التماثل', 'ربط التشخيص بقاعدة معتمدة', 'عرض النتيجة على المراجع'], 'methodology_rule_ar': '', 'requires_human_review': True}
            r = Record(id=rid, kind='objection', title_ar=(heading + ' ' + re.sub(r'\s+', ' ', wording)[:85]).strip(), objection_text_ar=wording, normalized_objection_ar=normalize_arabic(wording), source=cit, source_evidence={'capture_method': 'heading_section_v1', 'wording_status': 'candidate_source_passage_not_yet_verified_objection', 'source_hash': source['sha256'], 'coverage_start': start, 'coverage_end': end}, ai_analysis={'engine': 'conservative_regex_v1', 'proposal': analysis, 'created_at': now(), 'label_ar': 'استنتاج تحليلي'}, evidence_status='source_backed', evidence_label_ar='مدعوم من المصدر', tags=['source_candidate'], **analysis).model_dump()
            if store.add(r): made.append(r)
            captured.append(rid)
    if kind in ('all', 'rule'):
        seen = set()
        for match in RULE.finditer(text):
            start = text.rfind('\n', 0, match.start()) + 1
            end = min(len(text), match.end() + 200)
            next_end = text.find('\n', match.end() + 90, end)
            if next_end > 0: end = next_end
            cit = citation(source, mapping, start, end)
            raw = cit['source_excerpt']
            key = normalize_arabic(raw)
            if key in seen: continue
            seen.add(key)
            rid = 'RUL-' + digest([source_id, start, end, 'extract-v1'])[:12]
            r = Record(id=rid, kind='rule', title_ar='قاعدة مرشحة: ' + key[:90], source=cit, methodology_rule_ar=raw, primary_pattern=propose_pattern(raw), source_evidence={'capture_method': 'rule_anchor_v1', 'source_hash': source['sha256']}, ai_analysis={'engine': 'conservative_regex_v1', 'label_ar': 'استنتاج تحليلي', 'note_ar': 'تحديد حدود القاعدة ونسبتها إلى تقرير المؤلف، لا إلى القول المحكي، يحتاج مراجعة.'}, evidence_status='source_backed', evidence_label_ar='مدعوم من المصدر').model_dump()
            if store.add(r): made.append(r)
            captured.append(rid)
    # Every chunk has an inspectable inventory, even when no candidate was found.
    inventory = []
    for _, _, row in mapping:
        txt = row['text']
        inventory.append({'chunk_id': row['id'], 'page_number': row['page_number'], 'section': row['section'], 'has_rule_anchor': bool(RULE.search(txt)), 'diagnostic_questions': [m.group() for m in re.finditer(r'[^\n؟]{5,160}؟', txt)], 'comparison_markers': [m.group() for m in re.finditer(r'بين[^\n.]{3,140}', txt)], 'methodology_markers': [m.group() for m in re.finditer(r'(?:فيكون دورك|وجه الرد|وجه الجواب|فقل|فقلنا)[^\n]{0,160}', txt)], 'review_status': 'needs_review'})
    run = {'source_id': source_id, 'kind': kind, 'engine': 'conservative_regex_v1', 'at': now(), 'page_count': source.get('page_count'), 'chunks_scanned': len(mapping), 'detected_headings': len(heads), 'candidate_ids': captured, 'new_records': len(made), 'semantic_completeness': 'not_certified_requires_human_coverage_review', 'inventory': inventory}
    store.save_document('extraction_runs', run)
    folder = Path(data_dir) / 'pending_review'
    folder.mkdir(parents=True, exist_ok=True)
    for r in made: (folder / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    (Path(data_dir) / 'processed').mkdir(parents=True, exist_ok=True)
    (Path(data_dir) / 'processed' / f'{source_id}-coverage.json').write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding='utf-8')
    return run
