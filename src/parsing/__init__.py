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


def tokens(text):
    return re.findall(r'[\w]+', normalize_arabic(text).lower())
