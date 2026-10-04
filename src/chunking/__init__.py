import re


def semantic_chunks(text, max_chars=1800):
    """Contiguous page-local spans; heading/punctuation boundaries preferred."""
    start = 0
    headings = [m.start() for m in re.finditer(r'(?m)^(?:الفرع|الفصل|الباب)\s', text)]
    while start < len(text):
        end = min(start + max_chars, len(text))
        next_heading = next((h for h in headings if start < h < end), None)
        if next_heading is not None: end = next_heading
        if end < len(text) and next_heading is None:
            boundaries = list(re.finditer(r'\n(?=الفرع|الفصل|الباب)|[.؟]\s|\n\n', text[start:end]))
            useful = [m.end() for m in boundaries if m.end() > max_chars // 3]
            if useful: end = start + useful[-1]
            else:
                newline = text.rfind('\n', start + max_chars // 2, end)
                if newline >= 0: end = newline + 1
        yield start, end, text[start:end]
        start = end
