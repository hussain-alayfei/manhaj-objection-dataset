import re
import unicodedata


def normalize_arabic(text: str) -> str:
    """Search-only normalization. Never apply to source evidence."""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06edـ]', '', text)
    text = text.translate(str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي'}))
    # brackets carry no meaning for matching, and the book's extraction reversed their direction
    text = re.sub(r'[(){}\[\]<>«»﴿﴾"“”]', ' ', text)
    text = re.sub(r'\s*([،,.:؛!?؟])\s*', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()


def printed(text: str) -> str:
    """Book text as printed: the PDF extraction mirrored brackets (verses in {} appear as }...{) and left
    spaces before commas. Used for display-quality text sent to the analyst; stored evidence is untouched."""
    t = text or ''
    for o, c in (('{', '}'), ('(', ')'), ('[', ']')):
        i, j = t.find(o), t.find(c)
        if j != -1 and (i == -1 or j < i): t = t.translate(str.maketrans({o: c, c: o}))
    t = re.sub(r'\{\s*', '﴿', t); t = re.sub(r'\s*\}', '﴾', t)
    t = re.sub(r'"\s*([^"\n]{1,400}?)\s*"', r'«\1»', t)
    t = re.sub(r'([(\[«﴿])\s+', r'\1', t); t = re.sub(r'\s+([)\]»﴾])', r'\1', t)
    t = re.sub(r'[ \t]+([،؛:.!؟,])', r'\1', t)
    return t


def tokens(text):
    return re.findall(r'[\w]+', normalize_arabic(text).lower())
