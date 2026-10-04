import json
import pytest
from unittest.mock import patch

from src.chunking import semantic_chunks
from src.parsing import normalize_arabic
from src.parsing.extraction import extract_source
from src.research.pipeline import PublicFetcher, validate_url, research_common_objections


def test_arabic_normalization_preserves_original():
    source='إِنَّ الـبَيْعَ'
    assert normalize_arabic(source)=='ان البيع'
    assert source=='إِنَّ الـبَيْعَ'


def test_chunk_offsets_reconstitute_source():
    text=('عنوان\nفقرة عربية طويلة.\n'*200)+'نهاية'
    spans=list(semantic_chunks(text,250))
    assert ''.join(s[2] for s in spans)==text
    for start,end,value in spans:assert text[start:end]==value


def test_idempotent_extraction(store,tmp_path):
    a=extract_source(store,'SRC-test',data_dir=tmp_path)
    b=extract_source(store,'SRC-test',data_dir=tmp_path)
    assert a['new_records']>0 and b['new_records']==0
    assert a['chunks_scanned']==1


def test_research_cannot_fetch_before_gate(store,tmp_path):
    class Never:
        def fetch(self,*args):raise AssertionError('Network must not be reached')
    with pytest.raises(ValueError):research_common_objections('الوزن',1,store,tmp_path/'not-needed.json',Never())


@pytest.mark.parametrize('url', ['http://example.org/','https://user:secret@example.org/','https://example.org:8080/','https://evil.example/'])
def test_url_boundaries(url):
    with pytest.raises(ValueError):validate_url(url,'example.org')


def test_private_address_rejected():
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
        with pytest.raises(ValueError):validate_url('https://example.org/a','example.org')


def test_robots_denial():
    class Denied(PublicFetcher):
        def get(self,url,domain):return 'User-agent: *\nDisallow: /'
    with pytest.raises(ValueError):Denied().fetch('https://example.org/a',{'domain':'example.org'})
