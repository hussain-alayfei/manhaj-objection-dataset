"""Original-PDF storage: local disk for development, private Supabase Storage when hosted.

Object keys are derived from the source id (``<sid>/original.pdf``) so the immutable
source payload never has to change when files move between backends.
"""
import os
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent


def object_key(source_id):
    if not source_id or '/' in source_id or '..' in source_id: raise ValueError('Invalid source id')
    return f'{source_id}/original.pdf'


class LocalStorage:
    backend = 'local'

    def __init__(self, root=None):
        self.root = Path(root or ROOT / 'data' / 'source')

    def path(self, source_id, legacy_path=''):
        portable = self.root / object_key(source_id)
        return portable if portable.is_file() else Path(legacy_path or '')


class SupabaseStorage:
    """Minimal Storage REST client. The secret key travels in ``apikey`` (the gateway swaps sb_ keys)."""
    backend = 'supabase'

    def __init__(self, url=None, key=None, bucket=None, client=None):
        self.url = (url or os.getenv('SUPABASE_URL', '')).rstrip('/')
        self.key = key or os.getenv('SUPABASE_SECRET_KEY', '')
        self.bucket = bucket or os.getenv('SUPABASE_STORAGE_BUCKET', 'sources')
        if not self.url or not self.key: raise RuntimeError('STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SECRET_KEY')
        self.client = client or httpx.Client(timeout=60)

    def _headers(self, extra=None):
        return {'apikey': self.key, **(extra or {})}

    def _object(self, key):
        return f'{self.url}/storage/v1/object/{quote(self.bucket)}/{quote(key)}'

    def upload(self, source_id, data: bytes, upsert=False):
        response = self.client.post(self._object(object_key(source_id)), content=data, headers=self._headers({'Content-Type': 'application/pdf', 'x-upsert': 'true' if upsert else 'false'}))
        response.raise_for_status()
        return object_key(source_id)

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
