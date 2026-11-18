"""Split long text into overlapping chunks.

A pure function (no database, no AI), so it is trivial to test. Chunks prefer to
end at a natural boundary so that each one stays about a single topic:
paragraph break, then line break, then end of sentence, then a space. Only text
with no boundary at all (for example one huge token) is cut at the exact size.
"""

_SEPARATORS = ("\n\n", "\n", ". ", " ")


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """Return chunks of at most `size` characters; neighbours share about `overlap`.

    The overlap means a sentence cut at a boundary still appears whole in one chunk.
    """
    if size < 1:
        raise ValueError("size must be at least 1")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be between 0 and size - 1")

    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            end = _best_break(text, start, end, size)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = _next_start(text, start, end, overlap)
    return chunks


def _best_break(text: str, start: int, end: int, size: int) -> int:
    # Only look in the second half of the window, so chunks never get tiny.
    window_start = start + size // 2
    for separator in _SEPARATORS:
        index = text.rfind(separator, window_start, end)
        if index != -1:
            return index + len(separator)
    return end


def _next_start(text: str, start: int, end: int, overlap: int) -> int:
    # Always move forward, otherwise a large overlap could loop forever.
    candidate = max(end - overlap, start + 1)
    # Start the overlap on a word boundary instead of in the middle of a word.
    if candidate < end and not text[candidate - 1].isspace() and not text[candidate].isspace():
        j = candidate
        while j < end and not text[j].isspace():
            j += 1
        if j < end:
            candidate = j + 1
    return candidate
