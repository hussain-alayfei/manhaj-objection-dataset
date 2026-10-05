from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Pattern = Literal['جمع بين مختلفين', 'تفريق بين متماثلين', 'unknown', 'mixed_pattern', 'multiple_claims', 'insufficient_evidence', 'requires_human_review']
Status = Literal['draft', 'needs_review', 'approved', 'rejected']
SUBPATTERNS = {
    'جمع بين مختلفين': ['اختلاف المعنى', 'اختلاف السياق', 'اختلاف الحال', 'اختلاف الزمن', 'أصل ≠ وصف', 'فعل ≠ فاعل'],
    'تفريق بين متماثلين': ['لا يوجد فارق مؤثر', 'تشابه في محل الحكم', 'تطبيق معيارين مختلفين على حالتين متماثلتين'],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Span(Strict):
    chunk_id: str
    page_number: int | None = Field(default=None, ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)


class Citation(Strict):
    source_id: str
    source_type: Literal['book', 'external'] = 'book'
    source_name: str
    author: str = ''
    page_number: int | None = Field(default=None, ge=1)
    page_number_type: Literal['pdf_1_based', 'not_applicable'] = 'pdf_1_based'
    printed_page_number: str | None = None
    section: str = ''
    source_excerpt: str
    source_url: str | None = None
    source_date: str | None = None
    retrieved_at: str | None = None
    spans: list[Span] = Field(min_length=1)


class Comparison(Strict):
    entity_a: str
    entity_b: str


class Analysis(Strict):
    central_claim_ar: str = ''
    subclaims_ar: list[str] = Field(default_factory=list)
    key_terms_ar: list[str] = Field(default_factory=list)
    compared_entities_ar: list[Comparison] = Field(default_factory=list)
    primary_pattern: Pattern = 'unknown'
    sub_patterns: list[str] = Field(default_factory=list)
    diagnostic_reason_ar: str = ''
    revealing_question_ar: str = ''
    methodology_rule_ar: str = ''
    treatment_ar: str = ''
    response_path_ar: list[str] = Field(default_factory=list)
    methodology_rule_ids: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode='after')
    def compatible_subpatterns(self):
        allowed = SUBPATTERNS.get(self.primary_pattern, sum(SUBPATTERNS.values(), []))
        if any(p not in allowed for p in self.sub_patterns):
            raise ValueError('Sub-pattern does not belong to the selected taxonomy root')
        return self


SubPattern = Literal['اختلاف المعنى', 'اختلاف السياق', 'اختلاف الحال', 'اختلاف الزمن', 'أصل ≠ وصف', 'فعل ≠ فاعل', 'لا يوجد فارق مؤثر', 'تشابه في محل الحكم', 'تطبيق معيارين مختلفين على حالتين متماثلتين']


class AnalysisProposal(Strict):
    """Provider-facing schema for strict structured outputs: every field required, no defaults.

    Converted to ``Analysis`` (which keeps its defaults for records, exports, and JSON Schema)."""
    central_claim_ar: str
    subclaims_ar: list[str]
    key_terms_ar: list[str]
    compared_entities_ar: list[Comparison]
    primary_pattern: Pattern
    sub_patterns: list[SubPattern]
    diagnostic_reason_ar: str
    revealing_question_ar: str
    treatment_ar: str
    response_path_ar: list[str]
    methodology_rule_ids: list[str]
    confidence: float

    def to_analysis(self) -> Analysis:
        data = self.model_dump()
        data['confidence'] = min(1.0, max(0.0, data['confidence']))
        # Rule wording is always resolved from stored evidence, never accepted from the model.
        return Analysis(**data, methodology_rule_ar='', requires_human_review=True)


# ---------- The eleven-step method: how Manhaj thinks when an objection arrives ----------
# Provider-facing and strict (every field required, no defaults). The keys are generated in this
# order, so the model works through the steps in sequence; step 10 (the critical reviewer) is a
# separate call that reads the finished draft.
TextKind = Literal['آية', 'حديث', 'أثر', 'قول عالم']
Collection = Literal['bukhari', 'muslim', 'abudawud', 'tirmidhi', 'nasai', 'ibnmajah', 'malik', 'other', 'none']
TextStatus = Literal['ثابت', 'مختلف في ثبوته', 'غير ثابت', 'لم يُعرف مصدره']
Dimension = Literal['معنى اللفظ في لغة العرب', 'استعماله زمن النص', 'السياق', 'الحقيقة والمجاز', 'العموم والخصوص', 'الإطلاق والتقييد',
                    'دلالات الأعداد', 'التكثير والمبالغة', 'الاشتراك اللفظي', 'الكناية', 'الحذف', 'أساليب الخطاب']
ComparisonCheck = Literal['جمع بين مختلفين', 'تفريق بين متماثلين', 'عام وخاص', 'مطلق ومقيد', 'حصر أم تكثير', 'سياق مختلف', 'واقعة مختلفة', 'صحة متساوية']
Answer3 = Literal['نعم', 'لا', 'محتمل']
Verdict = Literal['مدعوم بالدليل', 'مرفوض', 'محتمل']
ConfidenceLabel = Literal['قطعي', 'راجح', 'توجيه معتبر غير قطعي', 'محتمل يحتاج نظرًا', 'ضعيف']
METHOD_STEPS = ('step1_framing', 'step2_entities', 'step3_sources', 'step4_related', 'step5_language', 'step6_comparison',
                'governing_rules', 'step7_hypotheses', 'step8_tests', 'step9_map', 'step11_answer')


class TextRef(Strict):
    kind: TextKind
    quote: str = Field(description='لفظ النص كما ورد، دون زيادة ولا تصرف')
    surah: int = Field(description='رقم السورة إن كان آية، وإلا 0')
    ayah: int = Field(description='رقم الآية إن كان آية، وإلا 0')
    collection: Collection = Field(description='الكتاب الذي خرّج الحديث إن كنت متيقنًا، وإلا none')
    number: int = Field(description='رقم الحديث في ذلك الكتاب إن كنت متيقنًا منه، وإلا 0')
    source_ar: str = Field(description='التخريج المختصر كما تعرفه يقينًا، أو: لم يُعرف مصدره')
    grade_ar: str = Field(description='درجته عند أهل الحديث إن عُرفت، وإلا فارغ')
    status: TextStatus


class Framing(Strict):
    claim: str = Field(description='الدعوى في جملة واحدة كما يقصدها السائل')
    evidence: list[str] = Field(description='ما استدل به السائل، بلفظه')
    conclusion: str = Field(description='النتيجة التي يريد الوصول إليها')
    premises: list[str] = Field(description='المقدمات الصريحة في كلامه')
    hidden_assumption: str = Field(description='الافتراض الخفي الذي تقوم عليه الشبهة ولم يصرّح به')


class Entities(Strict):
    verses: list[str]
    hadiths: list[str]
    key_words: list[str]
    numbers: list[str]
    persons: list[str]
    events: list[str]
    rulings: list[str]
    terms: list[str]
    claims: list[str] = Field(description='ادعاءات تاريخية أو علمية')


class SourceCheck(Strict):
    texts: list[TextRef] = Field(description='كل نص تقوم عليه الشبهة، مع درجة ثبوته')
    variants: str = Field(description='اختلاف الروايات وتمييز كل رواية بمصدرها، أو فارغ')


class Related(Strict):
    issue: str = Field(description='المسألة التي يدور عليها الباب، في عبارة قصيرة')
    other_texts: list[TextRef] = Field(description='نصوص أخرى في الباب تعرفها يقينًا')
    narrations: list[str]
    scholars: list[str] = Field(description='معنى ما قرره أهل العلم، مع اسم العالم أو الكتاب إن كنت متيقنًا')
    language: list[str]
    usul: list[str]
    context: list[str]


class Finding(Strict):
    dimension: Dimension
    finding: str


class Language(Strict):
    findings: list[Finding] = Field(description='الجوانب المؤثرة في فهم النص وحدها')


class Answered(Strict):
    answer: Answer3
    why: str


class CheckNote(Strict):
    check: ComparisonCheck
    finding: str


class SemanticComparison(Strict):
    side_a: str
    side_b: str
    same_thing: Answered
    same_aspect: Answered
    same_meaning: Answered
    checks: list[CheckNote] = Field(description='الاعتبارات المؤثرة في هذه المقارنة وحدها')
    conclusion: str


class Governing(Strict):
    primary_pattern: Pattern
    sub_patterns: list[SubPattern]
    fault: str = Field(description='موضع الخلل في عبارة قصيرة')
    explanation: str = Field(description='بيان الخلل في جملة واحدة')
    methodology_rule_ids: list[str] = Field(description='معرفات القواعد المرفقة التي يقوم عليها التشخيص')


class Hypothesis(Strict):
    id: str = Field(description='H1، H2، ...')
    title: str
    basis: str = Field(description='لماذا طُرحت هذه الفرضية')


class HypothesisTest(Strict):
    id: str
    verdict: Verdict
    evidence: str = Field(description='الدليل الذي يدعمها، أو سبب استبعادها')


class ArgumentMap(Strict):
    objection: str
    hidden_assumption: str
    fault: str
    evidence: str
    rule: str
    resolution: str = Field(description='إزالة التعارض')
    conclusion: str


class Dismantle(Strict):
    step: str
    evidence: str


class Answer(Strict):
    summary: str = Field(description='خلاصة الشبهة')
    origin: str = Field(description='منشأ الإشكال')
    dismantling: list[Dismantle] = Field(description='تفكيك الشبهة خطوة خطوة، ولكل خطوة دليلها')
    sources: list[str] = Field(description='الأدلة والمصادر التي بُني عليها الجواب')
    disagreement: str = Field(description='الخلاف المعتبر في المسألة إن وُجد، وإلا فارغ')
    revealing_question: str = Field(description='سؤال واحد يكشف للسائل موضع الخلل')
    confidence: float
    confidence_label: ConfidenceLabel


class MethodProposal(Strict):
    step1_framing: Framing
    step2_entities: Entities
    step3_sources: SourceCheck
    step4_related: Related
    step5_language: Language
    step6_comparison: SemanticComparison
    governing_rules: Governing
    step7_hypotheses: list[Hypothesis]
    step8_tests: list[HypothesisTest]
    step9_map: ArgumentMap
    step11_answer: Answer

    def to_analysis(self) -> Analysis:
        """The record-shaped summary that history, review and export already understand."""
        f, g, c, a = self.step1_framing, self.governing_rules, self.step6_comparison, self.step11_answer
        allowed = SUBPATTERNS.get(g.primary_pattern, sum(SUBPATTERNS.values(), []))
        return Analysis(
            central_claim_ar=f.claim, subclaims_ar=[*f.premises, *([f.hidden_assumption] if f.hidden_assumption.strip() else [])],
            key_terms_ar=[*self.step2_entities.key_words, *self.step2_entities.terms],
            compared_entities_ar=[Comparison(entity_a=c.side_a, entity_b=c.side_b)] if c.side_a.strip() and c.side_b.strip() else [],
            primary_pattern=g.primary_pattern, sub_patterns=[p for p in dict.fromkeys(g.sub_patterns) if p in allowed],
            diagnostic_reason_ar=' '.join(x for x in (g.fault.strip(), g.explanation.strip()) if x), revealing_question_ar=a.revealing_question,
            treatment_ar=self.step9_map.resolution, response_path_ar=[d.step for d in a.dismantling],
            methodology_rule_ids=list(dict.fromkeys(g.methodology_rule_ids)), confidence=min(1.0, max(0.0, a.confidence)),
            methodology_rule_ar='', requires_human_review=True)


class CriticCheck(Strict):
    ok: bool = Field(description='true إذا سلم الجواب من هذا الخلل')
    note: str


class CriticReport(Strict):
    """Step 10: a second layer that objects to the draft before anything is shown."""
    misunderstood: CriticCheck = Field(description='هل أسأنا فهم الشبهة؟')
    evidence_proves: CriticCheck = Field(description='هل الدليل يثبت النتيجة فعلًا؟')
    contrary_text: CriticCheck = Field(description='هل يوجد نص يعارض الجواب؟')
    unsourced_attribution: CriticCheck = Field(description='هل نُسب قولٌ لعالم دون مصدر؟')
    possibility_as_certainty: CriticCheck = Field(description='هل جُعل الاحتمال يقينًا؟')
    stronger_explanation: CriticCheck = Field(description='هل يوجد تفسير أقوى؟')
    holds: bool = Field(description='هل يصمد الجواب؟')
    revision: str = Field(description='ما يجب تصحيحه إن لم يصمد، وإلا فارغ')


class Record(Analysis):
    id: str
    kind: Literal['objection', 'rule', 'family']
    title_ar: str
    objection_text_ar: str = ''
    normalized_objection_ar: str = ''
    source: Citation | None = None
    source_evidence: dict = Field(default_factory=dict)
    ai_analysis: dict = Field(default_factory=dict)
    human_review: dict | None = None
    evidence_status: Literal['source_backed', 'analytical_inference', 'needs_review'] = 'needs_review'
    evidence_label_ar: Literal['مدعوم من المصدر', 'استنتاج تحليلي', 'يحتاج مراجعة'] = 'يحتاج مراجعة'
    review_status: Status = 'needs_review'
    reviewer_notes: str = ''
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    added_by: str = 'extractor'
    version: int = Field(default=1, ge=1)
    previous_version: int | None = None
    duplicate_group_id: str | None = None
    similarity_type: Literal['exact_duplicate', 'paraphrase', 'same_underlying_objection', 'same_pattern_different_objection', 'new_case'] = 'new_case'
    duplicate_candidates: list[dict] = Field(default_factory=list)
    family_id: str | None = None
    family_title_ar: str = ''
    core_claim_ar: str = ''
    core_confusion_ar: str = ''
    common_variants_ar: list[str] = Field(default_factory=list)
    common_sub_patterns: list[str] = Field(default_factory=list)
    methodology_rules: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    phase: Literal[1, 2] = 1


class ReviewRequest(Strict):
    expected_version: int = Field(ge=1)
    action: Literal['approve', 'edit', 'reject', 'reopen']
    changes: dict = Field(default_factory=dict)
    notes: str = Field(default='', max_length=5000)
    source_verified: bool = False
    page_verified: bool = False
    diagnosis_verified: bool = False

    # Every review is copied into append-only history several times, so its size is capped.
    @field_validator('changes')
    @classmethod
    def _bounded_changes(cls, value):
        import json as _json
        if len(_json.dumps(value, ensure_ascii=False)) > 60000: raise ValueError('التعديلات أطول من المسموح.')
        return value

