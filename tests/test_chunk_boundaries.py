from src.chunking import semantic_chunks


def test_heading_splits_a_short_page_without_changing_text():
    text='نهاية الفرع السابق.\nالفرع الثاني : مثال ثان.\nالفرع الثالث : مثال ثالث.'
    spans=list(semantic_chunks(text))
    assert len(spans)==3
    assert spans[1][2].startswith('الفرع الثاني')
    assert ''.join(x[2] for x in spans)==text
