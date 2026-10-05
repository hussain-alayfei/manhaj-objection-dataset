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

