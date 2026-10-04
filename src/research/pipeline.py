"""Opt-in source registry. No external collection before human source-coverage signoff."""
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import http.client
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import insert, select

from ..classification import diagnose
from ..llm import provider_errors
from ..db import chunks, digest, sources
from ..models import Record, now
from ..parsing import normalize_arabic
from ..parsing.extraction import citation

USER_AGENT = 'ManhajResearchBot/0.1'


def phase_fingerprint(store, conn=None):
    records = store.records(phase=1, conn=conn)
    book_sources = [(s['id'], s['sha256']) for s in store.source_list(conn) if s['source_type'] == 'book']
    return digest({'records': [(r['id'], r['version'], r['review_status']) for r in records if r['kind'] != 'family'], 'sources': book_sources})


def certify_phase_one(store, reviewer_id, coverage_verified, notes):
    if not coverage_verified or not notes.strip(): raise ValueError('Explicit human coverage verification and notes required')
    with store.transaction() as c:
        from ..db import reviewers
        if not c.execute(select(reviewers.c.id).where(reviewers.c.id == reviewer_id)).first(): raise ValueError('Unknown reviewer')
        records = [r for r in store.records(phase=1, conn=c) if r['kind'] != 'family']
        if not records or any(r['review_status'] not in ('approved', 'rejected') for r in records): raise ValueError('Finish every Phase 1 candidate review before enabling Phase 2')
        approved = store.eligible(conn=c)
        if not any(r['kind'] == 'rule' and r['phase'] == 1 for r in approved) or not any(r['kind'] == 'objection' and r['phase'] == 1 for r in approved): raise ValueError('Approved Phase 1 rules and examples required')
        books = [s for s in store.source_list(c) if s['source_type'] == 'book']
        runs = store.list_documents('extraction_runs', c)
        if any(not any(x['payload']['source_id'] == b['id'] and x['payload']['kind'] == 'all' for x in runs) for b in books): raise ValueError('A full extraction run is required for each book')
        return store.save_document('phase_gates', {'reviewer_id': reviewer_id, 'coverage_verified': True, 'notes': notes, 'at': now(), 'fingerprint': phase_fingerprint(store, c)}, conn=c)


def require_phase_two(store, conn=None):
    gates = store.list_documents('phase_gates', conn)
    fingerprint = phase_fingerprint(store, conn)
    if not any(g['payload']['fingerprint'] == fingerprint for g in gates): raise ValueError('Phase 2 is locked until Phase 1 human review and coverage signoff; changed records invalidate signoff')


def validate_url(url, domain):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.hostname != domain:
        raise ValueError('URL is outside the approved HTTPS domain')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError('Private/reserved network destinations are prohibited')
    return addresses[0][4][0]


class PublicFetcher:
    def __init__(self):
        self.last_fetch = {}

    def get(self, url, domain):
        address = validate_url(url, domain)
        # Pin the checked IP, retaining hostname verification and SNI: no DNS rebinding.
        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self):
                sock = socket.create_connection((address, 443), timeout=20)
                self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=domain)
        client = PinnedHTTPS(domain, timeout=20)
        parsed = urlparse(url)
        try:
            client.request('GET', parsed.path + ('?' + parsed.query if parsed.query else '') or '/', headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = client.getresponse()
            if response.status != 200: raise ValueError(f'HTTP {response.status}; redirects and missing robots policy fail closed')
            content_type = response.getheader('Content-Type', '')
            if 'text/' not in content_type: raise ValueError('Expected public text content')
            body = response.read(2_000_001)
            if len(body) > 2_000_000: raise ValueError('Response exceeds 2 MB')
            encoding = response.headers.get_content_charset() or 'utf-8'
            return body.decode(encoding, errors='strict')
        finally: client.close()

    def fetch(self, url, policy):
        domain = policy['domain']
        robots = RobotFileParser()
        robots.parse(self.get(f'https://{domain}/robots.txt', domain).splitlines())
        if not robots.can_fetch(USER_AGENT, url): raise ValueError('robots.txt disallows automated access')
        delay = max(float(policy.get('min_interval_seconds', 2)), float(robots.crawl_delay(USER_AGENT) or 0))
        if delay > 300: raise ValueError('Crawl delay exceeds this bounded job; schedule manually')
        remaining = delay - (time.monotonic() - self.last_fetch.get(domain, 0))
        if remaining > 0: time.sleep(remaining)
        self.last_fetch[domain] = time.monotonic()
        return self.get(url, domain)


def research_common_objections(topic, limit, store=None, registry_path='config/external_sources.json', fetcher=None, analyst=None):
    from ..db import Store
    store = store or Store()
    require_phase_two(store)
    if not topic.strip() or not 1 <= limit <= 50: raise ValueError('Topic required; limit must be 1-50')
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    fetcher = fetcher or PublicFetcher()
    results, errors = [], []
    known = {normalize_arabic(r['objection_text_ar']) for r in store.records('objection')}
    for policy in registry['sources']:
        if not policy.get('enabled') or not policy.get('automated_access_allowed') or not policy.get('rights_reviewed_by') or not policy.get('terms_url') or not policy.get('license_basis'): continue
        # Deliberately bounded search over operator-approved document URLs.
        for url in policy.get('urls', []):
            if len(results) >= limit: break
            try:
                html = fetcher.fetch(url, policy)
                soup = BeautifulSoup(html, 'html.parser')
                for elem in soup(['script', 'style', 'nav', 'footer']): elem.decompose()
                title = soup.title.get_text(' ', strip=True) if soup.title else url
                timestamp = soup.find('time')
                date = timestamp.get('datetime') if timestamp else None
                paragraphs = [p.get_text(' ', strip=True) for p in soup.select(policy.get('selector', 'p, li'))]
                for paragraph in paragraphs:
                    if len(results) >= limit: break
                    if len(paragraph) < 25 or not any(t in normalize_arabic(paragraph) for t in normalize_arabic(topic).split()): continue
                    if not re.search(r'؟|لماذا|كيف|شبهة|اعتراض', paragraph): continue
                    maximum = min(int(policy.get('max_excerpt_chars', 600)), 2000)
                    wording = paragraph[:maximum]
                    key = normalize_arabic(wording)
                    if key in known: continue
                    known.add(key)
                    sid = 'EXT-' + digest([url, wording])[:16]
                    retrieved = now()
                    src = {'id': sid, 'source_type': 'external', 'source_name': title, 'author': policy.get('author', ''), 'source_url': url, 'source_date': date, 'retrieved_at': retrieved, 'sha256': hashlib.sha256(wording.encode()).hexdigest(), 'rights': {k: policy[k] for k in ('license_basis', 'terms_url', 'rights_reviewed_by')}, 'wording_type': 'verbatim_excerpt', 'truncated': len(paragraph) > maximum}
                    cid = sid + '-C001'
                    with store.transaction() as c:
                        require_phase_two(store, c)
                        if not c.execute(select(sources.c.id).where(sources.c.id == sid)).first():
                            # URL+excerpt hash distinguishes independent citation provenance.
                            c.execute(insert(sources).values(id=sid, sha256=digest([url, wording]), payload=src))
                            c.execute(insert(chunks).values(id=cid, source_id=sid, page_number=None, section='', text=wording, raw_text=wording, payload={'retrieved_at': retrieved}))
                    cit = citation(src, [(0, len(wording), {'id': cid, 'page_number': None, 'text': wording})], 0, len(wording))
                    proposal = diagnose(store, wording, analyst=analyst)
                    r = Record(id='SHB-' + digest([sid, wording])[:12], kind='objection', title_ar=wording[:90], objection_text_ar=wording, normalized_objection_ar=key, source=cit, source_evidence={'wording_type': 'verbatim_excerpt', 'rights': src['rights'], 'retrieved_at': retrieved}, ai_analysis=proposal, evidence_status='analytical_inference', evidence_label_ar='استنتاج تحليلي', phase=2, tags=[topic, 'external_candidate'], **proposal['analysis']).model_dump()
                    with store.transaction() as c:
                        require_phase_two(store, c)
                        store.add(r, c)
                    results.append(r['id'])
            except (*provider_errors(), KeyError, OSError) as exc:
                errors.append({'url': url, 'error': str(exc)})
    duplicate_run_id = None
    if results:
        from ..duplicate_detection import detect_duplicates
        from ..retrieval.hybrid import SemanticEncoder
        import os
        duplicate_run_id = detect_duplicates(store, SemanticEncoder() if os.getenv('EMBEDDING_MODEL') else None)['id']
    return {'record_ids': results, 'errors': errors, 'duplicate_run_id': duplicate_run_id, 'review_status': 'needs_review', 'search_scope': 'configured_public_document_urls'}
