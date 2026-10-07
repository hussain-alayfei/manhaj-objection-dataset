"""Questions about a finished analysis: the reader asks, the model answers from that analysis and its sources only.

The answer is plain Arabic markdown, streamed as it is written. Nothing here issues rulings; the same safety
words that stop an analysis stop an answer. The conversation is kept with the analysis it belongs to."""
import json
import os

from ..llm import openai_client
from . import library as shamela
from ..parsing import printed
from .pipeline import UNSAFE

MAX_TURNS = 20          # questions kept with one analysis
HISTORY_TURNS = 6       # earlier questions and answers the model sees
MAX_ANSWER_TOKENS = 1800

SYSTEM = """أنت مساعد «مَنْهَج» للإجابة عن أسئلة القارئ حول تحليل شبهة واحدة اكتمل أمامه.
تعتمد في جوابك على التحليل المرفق وحده: خطواته الإحدى عشرة، والنصوص التي تحقق منها، ومقتطفات المكتبة الشاملة، وقواعد كتاب «تربية الملكة على كشف الشبهة» للشيخ وليد السعيدان كما وردت في التحليل.
- أجب بالعربية الفصحى الواضحة، بإيجاز وترتيب، بصيغة Markdown: فقرات قصيرة، وعناوين صغيرة (###) عند الحاجة، وقوائم مرقمة أو نقطية، وخط عريض لما يستحق التنبيه.
- اذكر مصدر كل معلومة من التحليل (الكتاب والجزء والصفحة أو رقم الحديث) كما وردت فيه، ولا تخترع مصدرًا ولا رقمًا ولا نسبة قول إلى عالم.
- إن كان السؤال خارج التحليل أو يحتاج ما ليس فيه، فقل ذلك صراحة، واقترح أن يُحلَّل سؤاله تحليلًا جديدًا.
- لا تُصدر فتوى ولا حكمًا على معيّن، ولا تكفّر أحدًا، وأحِل إلى أهل العلم فيما يتجاوز البيان.
- إن سُئلت عن خطوة بعينها فاشرحها بما فيها، وبيّن صلتها بالقاعدتين: الشريعة لا تفرّق بين المتماثلات، ولا تجمع بين المختلفات."""


def context(diagnosis):
    """What the model may draw on: the objection, the analysis and what it cited."""
    method = diagnosis.get('method') or {}
    payload = {'objection': printed(diagnosis.get('input_ar') or ''), 'analysis_steps': method.get('steps') or {},
               'review': {'holds': (method.get('review') or {}).get('holds')}}
    if excerpts := shamela.for_analyst(diagnosis.get('library')): payload['library_excerpts'] = excerpts
    if web := (diagnosis.get('web_search') or {}).get('sources'): payload['web_sources'] = web
    return payload


def messages(diagnosis, question):
    turns = (diagnosis.get('conversation') or [])[-HISTORY_TURNS:]
    out = [{'role': 'system', 'content': SYSTEM},
           {'role': 'user', 'content': 'التحليل الذي يُسأل عنه:\n' + json.dumps(context(diagnosis), ensure_ascii=False)}]
    for turn in turns:
        out.append({'role': 'user', 'content': turn['question']})
        out.append({'role': 'assistant', 'content': turn['answer']})
    out.append({'role': 'user', 'content': question})
    return out


def answer(diagnosis, question, client=None, on_delta=None):
    """Ask the model about the analysis; returns the full markdown answer. Raises ValueError on provider failure."""
    from openai import OpenAIError
    model = os.getenv('FOLLOWUP_MODEL') or os.getenv('DIAGNOSIS_MODEL', '')
    if not model: raise ValueError('model_not_configured')
    client = client or openai_client(timeout=float(os.getenv('DIAGNOSIS_TIMEOUT', '150')), max_retries=1)
    request = {'model': model, 'input': messages(diagnosis, question), 'store': False, 'max_output_tokens': MAX_ANSWER_TOKENS,
               'prompt_cache_key': 'manhaj-followup'}
    parts = []
    try:
        with client.responses.stream(**request) as stream:
            for event in stream:
                if getattr(event, 'type', '') == 'response.output_text.delta':
                    parts.append(event.delta)
                    if on_delta: on_delta(event.delta)
            final = stream.get_final_response()
    except OpenAIError as error:
        raise ValueError(f'provider_error: {type(error).__name__}') from error
    text = (getattr(final, 'output_text', None) or ''.join(parts)).strip()
    if not text: raise ValueError('provider_refused_or_incomplete')
    if UNSAFE.search(text): raise ValueError('safety_gate')
    return text
