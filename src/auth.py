"""Reviewer accounts: password hashing, session tokens and input checks.

Passwords are hashed with scrypt (standard library, memory-hard). Sessions are random bearer
tokens; only their SHA-256 is stored, so a database leak does not reveal usable tokens.
"""
import base64
import hashlib
import hmac
import re
import secrets
import time
import unicodedata

SESSION_DAYS = 30
_N, _R, _P = 2 ** 14, 8, 1
EMAIL = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,63}$')


def _b64(data):
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f'scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(key)}'


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, key = stored.split('$')
        if scheme != 'scrypt': return False
        expected = base64.b64decode(key)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Checked against when an email is unknown, so a failed login takes the same time either way.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def now_s() -> int:
    return int(time.time())


def clean_email(value: str) -> str:
    email = unicodedata.normalize('NFKC', value or '').strip().lower()
    if len(email) > 254 or not EMAIL.match(email): raise ValueError('اكتب بريدًا إلكترونيًا صحيحًا.')
    return email


def clean_name(value: str) -> str:
    name = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value or '')).strip()
    if any(unicodedata.category(c).startswith('C') for c in name): raise ValueError('الاسم يحتوي على رموز غير مسموحة.')
    if not 2 <= len(name) <= 60: raise ValueError('اكتب اسمًا من حرفين إلى 60 حرفًا.')
    return name


def check_new_password(password: str, email: str) -> str:
    if not 8 <= len(password or '') <= 200: raise ValueError('كلمة المرور من 8 أحرف على الأقل.')
    if password.strip().lower() in (email, email.split('@')[0]): raise ValueError('اختر كلمة مرور مختلفة عن بريدك.')
    return password
