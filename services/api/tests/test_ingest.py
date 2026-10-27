from pathlib import Path

import pytest

from app.retrieval.embeddings import EMBEDDING_DIM, to_pgvector
from app.retrieval.ingest import (
    PERSONA_ROLES,
    Document,
    chunk_document,
    load_documents,
    parse_document,
)


def _write(tmp_path: Path, name: str, front_matter: str, body: str = "# T\n\nIntro.") -> Path:
    docs = tmp_path / "data" / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / name
    path.write_text(f"---\n{front_matter}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _doc(body: str) -> Document:
    return Document("d", "Title", ("r_finance",), None, body, "data/documents/d.md", "h")


def test_repository_documents_are_valid() -> None:
    docs = load_documents()
    assert len(docs) >= 15
    for doc in docs:
        assert set(doc.allowed_roles) <= PERSONA_ROLES
        assert chunk_document(doc), doc.doc_id


def test_parse_document_reads_front_matter(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "guide.md",
        "id: guide\ntitle: Guide\nallowed_roles: [r_sales_rep]\nregion: NZ-SOUTH",
    )
    doc = parse_document(path, root=path.parent)
    assert doc.allowed_roles == ("r_sales_rep",)
    assert doc.region == "NZ-SOUTH"
    assert doc.source_path == "data/documents/guide.md"


@pytest.mark.parametrize(
    "front_matter",
    [
        "id: bad\ntitle: T\nallowed_roles: [r_admin]\nregion: null",
        "id: bad\ntitle: T\nallowed_roles: []\nregion: null",
        "id: bad\ntitle: T\nallowed_roles: [r_finance]\nregion: MARS",
        "id: other\ntitle: T\nallowed_roles: [r_finance]\nregion: null",
    ],
)
def test_parse_document_rejects_bad_front_matter(tmp_path: Path, front_matter: str) -> None:
    path = _write(tmp_path, "bad.md", front_matter)
    with pytest.raises(ValueError):
        parse_document(path, root=path.parent)


def test_chunks_follow_sections() -> None:
    chunks = chunk_document(_doc("# Title\n\nIntro text.\n\n## Terms\n\nPay in 30 days."))
    assert [(c.section, c.content) for c in chunks] == [
        ("Overview", "Intro text."),
        ("Terms", "Pay in 30 days."),
    ]
    assert [c.chunk_id for c in chunks] == ["d#0", "d#1"]


def test_long_sections_split_at_paragraphs() -> None:
    paragraph = "word " * 60
    chunks = chunk_document(_doc("## Long\n\n" + "\n\n".join([paragraph] * 5)), max_chars=700)
    assert len(chunks) > 1
    assert all(c.section == "Long" for c in chunks)
    assert all(len(c.content) <= 700 for c in chunks)


def test_empty_sections_make_no_chunks() -> None:
    chunks = chunk_document(_doc("# Title\n\n## Empty\n\n## Full\n\nText."))
    assert [c.section for c in chunks] == ["Full"]


def test_to_pgvector_checks_dimension() -> None:
    assert to_pgvector([0.5] * EMBEDDING_DIM).startswith("[0.5,0.5")
    with pytest.raises(ValueError):
        to_pgvector([0.5, 0.5])
