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
# local part: letters, digits and . _ % + - (no leading, trailing or doubled dot); domain: proper labels and a
# letters-only ending of 2+ characters. Covers every ordinary address and rejects the usual slips.
EMAIL = re.compile(r'^(?!\.)(?!.*\.\.)[A-Za-z0-9._%+-]{1,64}(?<!\.)@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$')
# common misspellings of big providers: suggest the right one instead of creating an unreachable account
TYPOS = {'gmial.com': 'gmail.com', 'gmai.com': 'gmail.com', 'gmail.co': 'gmail.com', 'gmail.con': 'gmail.com', 'gmail.cm': 'gmail.com', 'gamil.com': 'gmail.com',
         'gmal.com': 'gmail.com', 'hotmial.com': 'hotmail.com', 'hotmail.con': 'hotmail.com', 'hotmai.com': 'hotmail.com', 'outlok.com': 'outlook.com',
         'outlook.con': 'outlook.com', 'yaho.com': 'yahoo.com', 'yahoo.con': 'yahoo.com', 'icloud.con': 'icloud.com', 'iclod.com': 'icloud.com'}
COMMON = {'12345678', '123456789', '1234567890', 'password', 'password1', 'qwerty123', 'qwertyui', '11111111', '00000000', 'abcd1234', '87654321', 'aa123456', 'asdf1234'}


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
    if len(email) > 254 or not EMAIL.match(email): raise ValueError('البريد الإلكتروني غير صحيح. مثال صحيح: name@example.com')
    domain = email.rsplit('@', 1)[1]
    if domain in TYPOS: raise ValueError(f'هل تقصد {email.rsplit("@", 1)[0]}@{TYPOS[domain]}؟ تحقق من البريد.')
    return email


def clean_name(value: str) -> str:
    name = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value or '')).strip()
    if any(unicodedata.category(c).startswith('C') for c in name): raise ValueError('الاسم يحتوي على رموز غير مسموحة.')
    if not 2 <= len(name) <= 60: raise ValueError('اكتب اسمًا من حرفين إلى 60 حرفًا.')
    return name


def check_new_password(password: str, email: str) -> str:
    """Medium rules: 8+ characters with at least one letter and one digit, not a well-known password, not the email."""
    password = password or ''
    if not 8 <= len(password) <= 200: raise ValueError('كلمة المرور من 8 أحرف على الأقل.')
    if password != password.strip(): raise ValueError('لا تبدأ كلمة المرور بمسافة ولا تنتهِ بها.')
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password): raise ValueError('كلمة المرور تحتاج حرفًا ورقمًا على الأقل.')
    if password.lower() in COMMON or len(set(password)) < 4: raise ValueError('كلمة المرور سهلة التخمين. اختر غيرها.')
    if email and (password.lower() == email or password.lower() == email.split('@')[0] or email.split('@')[0] in password.lower() and len(email.split('@')[0]) >= 5):
        raise ValueError('اختر كلمة مرور لا تحتوي على بريدك.')
    return password
