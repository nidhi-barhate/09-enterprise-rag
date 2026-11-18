import pytest

from app.services.chunker import chunk_text

PARAGRAPHS = [
    "Check replica lag on the standby before doing anything else.",
    "Stop writes on the primary so the replica can catch up completely.",
    "Promote the replica to primary and update the connection string.",
    "Verify that writes succeed and the application is healthy again.",
]
TEXT = "\n\n".join(PARAGRAPHS)


def test_blank_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("  \n\t ") == []


def test_short_text_is_one_chunk():
    assert chunk_text("  just a short note  ", size=100, overlap=10) == ["just a short note"]


def test_text_exactly_at_size_is_one_chunk():
    assert chunk_text("a" * 50, size=50, overlap=10) == ["a" * 50]


@pytest.mark.parametrize("size,overlap", [(0, 0), (-5, 0), (10, -1), (10, 10), (10, 20)])
def test_invalid_parameters_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", size=size, overlap=overlap)


def test_no_chunk_is_longer_than_size():
    chunks = chunk_text(TEXT, size=80, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)


def test_prefers_paragraph_boundaries():
    chunks = chunk_text(TEXT, size=130, overlap=0)
    # Each chunk is made of whole paragraphs, never a paragraph cut in half.
    for chunk in chunks:
        for part in chunk.split("\n\n"):
            assert part in PARAGRAPHS


def test_every_word_survives_chunking():
    chunks = chunk_text(TEXT, size=70, overlap=20)
    original = set(TEXT.split())
    kept = {word for chunk in chunks for word in chunk.split()}
    assert kept == original


def test_words_are_never_cut_in_half():
    chunks = chunk_text(TEXT, size=45, overlap=15)
    original = set(TEXT.split())
    for chunk in chunks:
        assert set(chunk.split()) <= original


def test_neighbouring_chunks_overlap():
    sentence_text = " ".join(f"Sentence number {i} is here." for i in range(40))
    chunks = chunk_text(sentence_text, size=120, overlap=40)
    assert len(chunks) > 2
    for previous, following in zip(chunks, chunks[1:]):
        # the start of the next chunk repeats words from the end of the previous one
        assert following.split()[0] in previous.split()[-8:]


def test_zero_overlap_chunks_do_not_repeat_text():
    chunks = chunk_text(TEXT, size=130, overlap=0)
    assert "\n\n".join(chunks) == TEXT


def test_text_without_any_boundary_is_hard_cut_and_terminates():
    chunks = chunk_text("x" * 2500, size=1000, overlap=100)
    assert all(len(c) <= 1000 for c in chunks)
    assert len(chunks) == 3
    assert chunks[0] == "x" * 1000


def test_overlap_close_to_size_still_terminates():
    chunks = chunk_text("word " * 300, size=50, overlap=49)
    assert chunks
    assert all(len(c) <= 50 for c in chunks)


def test_size_one_terminates():
    assert chunk_text("a b c", size=1, overlap=0) == ["a", "b", "c"]


def test_chunking_is_deterministic():
    assert chunk_text(TEXT, size=60, overlap=10) == chunk_text(TEXT, size=60, overlap=10)
