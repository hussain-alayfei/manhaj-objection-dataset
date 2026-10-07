"""Original-PDF storage: local disk for development, private Supabase Storage when hosted.

Object keys are derived from the source id (``<sid>/original.pdf``) so the immutable
source payload never has to change when files move between backends.
"""
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent


def object_key(source_id):
    if not isinstance(source_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', source_id): raise ValueError('Invalid source id')
    return f'{source_id}/original.pdf'


def page_key(source_id, number):
    """Rendered page image used by the in-site book viewer (1-based PDF page number)."""
    object_key(source_id)
    if not isinstance(number, int) or number < 1: raise ValueError('Invalid page number')
    return f'{source_id}/pages/{number:04d}.webp'


class LocalStorage:
    backend = 'local'

    def __init__(self, root=None):
        self.root = Path(root or ROOT / 'data' / 'source')

    def path(self, source_id, legacy_path=''):
        portable = self.root / object_key(source_id)
        return portable if portable.is_file() else Path(legacy_path or '')

    def page_path(self, source_id, number):
        return self.root / page_key(source_id, number)


class SupabaseStorage:
    """Minimal Storage REST client. The secret key travels in ``apikey`` (the gateway swaps sb_ keys)."""
    backend = 'supabase'

    def __init__(self, url=None, key=None, bucket=None, client=None):
        self.url = (url or os.getenv('SUPABASE_URL', '')).rstrip('/')
        self.key = key or os.getenv('SUPABASE_SECRET_KEY', '')
        self.bucket = bucket or os.getenv('SUPABASE_STORAGE_BUCKET', 'sources')
        if not self.url or not self.key: raise RuntimeError('STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SECRET_KEY')
        self._client = client

    @property
    def client(self):
        # built on first use, not at start-up: most requests never touch the bucket
        if self._client is None: self._client = httpx.Client(timeout=60)
        return self._client

    def _headers(self, extra=None):
        return {'apikey': self.key, **(extra or {})}

    def _object(self, key):
        return f'{self.url}/storage/v1/object/{quote(self.bucket)}/{quote(key)}'

    def upload(self, source_id, data: bytes, upsert=False):
        return self.upload_object(object_key(source_id), data, 'application/pdf', upsert)

    def upload_object(self, key, data: bytes, content_type, upsert=False):
        response = self.client.post(self._object(key), content=data, headers=self._headers({'Content-Type': content_type, 'x-upsert': 'true' if upsert else 'false', 'cache-control': 'max-age=31536000'}))
        response.raise_for_status()
        return key

    def signed_urls(self, keys, expires_in=600):
        """Sign many objects in one request (book viewer pages)."""
        if not keys: return {}
        response = self.client.post(f'{self.url}/storage/v1/object/sign/{quote(self.bucket)}', json={'expiresIn': expires_in, 'paths': list(keys)}, headers=self._headers())
        response.raise_for_status()
        out = {}
        for item in response.json():
            signed = item.get('signedURL') or item.get('signedUrl')
            if signed and not item.get('error'):
                out[item['path']] = signed if signed.startswith('http') else f'{self.url}/storage/v1{signed}'
        return out

    def signed_url(self, source_id, expires_in=60):
        key = object_key(source_id)
        response = self.client.post(f'{self.url}/storage/v1/object/sign/{quote(self.bucket)}/{quote(key)}', json={'expiresIn': expires_in}, headers=self._headers())
        if response.status_code in (400, 404): raise KeyError(source_id)
        response.raise_for_status()
        signed = response.json().get('signedURL') or response.json().get('signedUrl')
        if not signed: raise ValueError('Storage did not return a signed URL')
        # Storage returns a path relative to /storage/v1.
        return signed if signed.startswith('http') else f'{self.url}/storage/v1{signed}'


def get_storage():
    backend = os.getenv('STORAGE_BACKEND', 'local').strip().lower()
    if backend == 'supabase': return SupabaseStorage()
    if backend == 'local': return LocalStorage()
    raise RuntimeError('STORAGE_BACKEND must be local or supabase')
