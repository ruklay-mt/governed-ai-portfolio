"""Load policy documents into retrieval.documents and retrieval.doc_chunks (spec §5.3).

Each markdown file in data/documents/ has YAML front matter (`id`, `title`, `allowed_roles`,
`region`). Files are split at `##` headings, embedded with Voyage and written as the database
owner. Unchanged files are skipped by content hash, so the daily pipeline re-embeds only what
changed. Files removed from the folder are removed from the database.

Usage: python -m app.retrieval.ingest --target dev|prod
"""

import argparse
import hashlib
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
import yaml

from app.config import get_settings
from app.retrieval.embeddings import Embedder, to_pgvector

DOCUMENTS_DIR = Path(__file__).resolve().parents[4] / "data" / "documents"
TARGET_ENV_VARS = {"dev": "DATABASE_URL", "prod": "DATABASE_URL_PROD"}
# Must match the persona roles in data/sql/migrations/0003_roles.sql. The RLS policy calls
# pg_has_role on each name, which errors on an unknown role, so names are checked here first.
PERSONA_ROLES = frozenset({"r_sales_rep", "r_sales_manager", "r_finance", "r_support"})
REGIONS = frozenset({"NZ-NORTH", "NZ-SOUTH", "AU-EAST", "AU-WEST"})
# About 400 tokens. Most sections are far shorter; longer ones are split at paragraphs.
MAX_CHUNK_CHARS = 1600

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    allowed_roles: tuple[str, ...]
    region: str | None
    body: str
    source_path: str
    content_hash: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    section: str
    content: str

    def embedding_text(self, doc_title: str) -> str:
        return f"{doc_title}\n{self.section}\n\n{self.content}"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_document(path: Path, root: Path = DOCUMENTS_DIR) -> Document:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing front matter")
    front_matter, body = text[4:].split("\n---\n", 1)
    meta = yaml.safe_load(front_matter)

    roles = tuple(meta["allowed_roles"])
    unknown = set(roles) - PERSONA_ROLES
    if not roles or unknown:
        raise ValueError(f"{path.name}: bad allowed_roles {sorted(unknown) or roles}")
    region = meta.get("region")
    if region is not None and region not in REGIONS:
        raise ValueError(f"{path.name}: unknown region {region}")
    if meta["id"] != path.stem:
        raise ValueError(f"{path.name}: id must match the file name")

    return Document(
        doc_id=meta["id"],
        title=meta["title"],
        allowed_roles=roles,
        region=region,
        body=body.strip(),
        source_path=str(path.relative_to(root.parent.parent)),
        content_hash=sha256(text),
    )


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split text at blank lines into pieces no longer than max_chars where possible."""
    pieces: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_document(doc: Document, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """One chunk per `##` section; the text before the first section becomes "Overview"."""
    sections: list[tuple[str, str]] = []
    heading = "Overview"
    lines: list[str] = []
    for line in doc.body.splitlines():
        if line.startswith("# "):
            continue  # the document title, already stored separately
        if line.startswith("## "):
            sections.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    sections.append((heading, "\n".join(lines).strip()))

    chunks: list[Chunk] = []
    for section, content in sections:
        for piece in _split_long(content, max_chars) if content else []:
            index = len(chunks)
            chunks.append(Chunk(f"{doc.doc_id}#{index}", doc.doc_id, index, section, piece))
    return chunks


def load_documents(root: Path = DOCUMENTS_DIR) -> list[Document]:
    return [parse_document(path, root) for path in sorted(root.glob("*.md"))]


@dataclass
class SyncStats:
    embedded: list[str]
    unchanged: list[str]
    removed: list[str]
    chunks: int


def sync(conn: psycopg.Connection, docs: Sequence[Document], embed: EmbedFn) -> SyncStats:
    """Bring the retrieval tables in line with `docs`, in one transaction."""
    stats = SyncStats(embedded=[], unchanged=[], removed=[], chunks=0)
    with conn.transaction():
        stored: dict[str, str] = dict(
            conn.execute("select doc_id, content_hash from retrieval.documents").fetchall()
        )
        changed = [doc for doc in docs if stored.get(doc.doc_id) != doc.content_hash]
        stats.unchanged = [doc.doc_id for doc in docs if doc not in changed]
        # One embedding call for everything that changed: fewer requests under Voyage rate limits.
        chunks_by_doc = {doc.doc_id: chunk_document(doc) for doc in changed}
        all_vectors = embed(
            [
                chunk.embedding_text(doc.title)
                for doc in changed
                for chunk in chunks_by_doc[doc.doc_id]
            ]
        )
        offset = 0
        for doc in changed:
            chunks = chunks_by_doc[doc.doc_id]
            vectors = all_vectors[offset : offset + len(chunks)]
            offset += len(chunks)
            conn.execute(
                "insert into retrieval.documents"
                " (doc_id, title, source_path, allowed_roles, region, content_hash)"
                " values (%s, %s, %s, %s, %s, %s)"
                " on conflict (doc_id) do update set title = excluded.title,"
                " source_path = excluded.source_path, allowed_roles = excluded.allowed_roles,"
                " region = excluded.region, content_hash = excluded.content_hash,"
                " updated_at = now()",
                (
                    doc.doc_id,
                    doc.title,
                    doc.source_path,
                    list(doc.allowed_roles),
                    doc.region,
                    doc.content_hash,
                ),
            )
            conn.execute("delete from retrieval.doc_chunks where doc_id = %s", (doc.doc_id,))
            for chunk, vector in zip(chunks, vectors, strict=True):
                conn.execute(
                    "insert into retrieval.doc_chunks (chunk_id, doc_id, chunk_index, doc_title,"
                    " section, content, content_hash, embedding, allowed_roles, region)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)",
                    (
                        chunk.chunk_id,
                        doc.doc_id,
                        chunk.chunk_index,
                        doc.title,
                        chunk.section,
                        chunk.content,
                        sha256(chunk.content),
                        to_pgvector(vector),
                        list(doc.allowed_roles),
                        doc.region,
                    ),
                )
            stats.embedded.append(doc.doc_id)
            stats.chunks += len(chunks)

        removed = sorted(set(stored) - {doc.doc_id for doc in docs})
        if removed:
            conn.execute("delete from retrieval.documents where doc_id = any(%s)", (removed,))
        stats.removed = removed
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGET_ENV_VARS), default="dev")
    args = parser.parse_args()

    database_url = os.environ.get(TARGET_ENV_VARS[args.target], "").strip()
    if not database_url:
        print(f"{TARGET_ENV_VARS[args.target]} is not set (see .env.example)", file=sys.stderr)
        return 1

    embedder = Embedder(get_settings())
    docs = load_documents()
    with psycopg.connect(database_url) as conn:
        stats = sync(conn, docs, lambda texts: embedder.embed(texts, "document"))
    print(
        f"{args.target}: embedded {len(stats.embedded)} documents ({stats.chunks} chunks),"
        f" unchanged {len(stats.unchanged)}, removed {len(stats.removed)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
