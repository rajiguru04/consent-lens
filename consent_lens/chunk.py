"""Clause-boundary chunking.

NOT fixed token windows. The product promise is "the spec says X, here, in clause Y"
and a citation that points at half a clause is not a citation. Chunk boundaries are
therefore a user-facing requirement that reaches back into parsing.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import asdict, dataclass

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"


@dataclass
class Chunk:
    doc_id: str
    doc_title: str
    authority: str          # regulation | specification | sro-guidance
    clause_id: str          # the thing a human can look up
    text: str
    retrieved_at: str

    def citation(self) -> str:
        return f"{self.doc_title}, {self.clause_id} (retrieved {self.retrieved_at[:10]})"


# Markdown: split on headings, carry the heading path as the clause id.
def chunk_markdown(raw: str, meta: dict) -> list[Chunk]:
    chunks, path, buf = [], [], []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body and path:
            chunks.append(
                Chunk(
                    doc_id=meta["id"],
                    doc_title=meta["title"],
                    authority=meta["authority"],
                    clause_id=" > ".join(path),
                    text=body,
                    retrieved_at=meta["retrieved_at"],
                )
            )

    for line in raw.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            buf = []
            depth = len(m.group(1))
            path = path[: depth - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    flush()
    return chunks


# Numbered legal text: split on clause numbers like "6.3" / "17." / "(4)".
CLAUSE_RE = re.compile(r"^\s*((?:\d+\.)+\d*|\(\d+\)|\d+\.)\s+(?=\S)", re.M)


def chunk_numbered(raw: str, meta: dict) -> list[Chunk]:
    marks = list(CLAUSE_RE.finditer(raw))
    if not marks:
        # Honest fallback: page/para anchors rather than pretending we found clauses.
        return _chunk_paragraph_anchored(raw, meta)
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        body = raw[m.start():end].strip()
        if len(body) < 40:
            continue
        out.append(
            Chunk(
                doc_id=meta["id"],
                doc_title=meta["title"],
                authority=meta["authority"],
                clause_id=f"cl. {m.group(1).rstrip('.')}",
                text=body,
                retrieved_at=meta["retrieved_at"],
            )
        )
    return out


def _chunk_paragraph_anchored(raw: str, meta: dict) -> list[Chunk]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if len(p.strip()) > 80]
    return [
        Chunk(
            doc_id=meta["id"],
            doc_title=meta["title"],
            authority=meta["authority"],
            clause_id=f"para {i+1} (no clause numbering found)",
            text=p,
            retrieved_at=meta["retrieved_at"],
        )
        for i, p in enumerate(paras)
    ]


def chunk_faq(text: str, meta: dict) -> list[Chunk]:
    """FAQ accordion pages (e.g. a Bootstrap panel-title/panel-body layout): one
    chunk per question, clause_id is the question itself — the most legible,
    verifiable citation this shape of content can offer, since there are no
    clause numbers to cite instead. Operates on strip_html's output rather than
    re-parsing raw nested HTML: strip_html already turns heading/paragraph tag
    boundaries into blank lines, so a short blank-line-delimited block ending in
    "?" is a reliable enough signal of "this is a question" without needing to
    track HTML tag nesting.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks: list[Chunk] = []
    question: str | None = None
    answer_parts: list[str] = []

    def flush() -> None:
        body = " ".join(answer_parts).strip()
        if question and len(body) > 20:
            chunks.append(Chunk(
                doc_id=meta["id"], doc_title=meta["title"], authority=meta["authority"],
                clause_id=question, text=f"{question} {body}",
                retrieved_at=meta["retrieved_at"]))

    for b in blocks:
        if b.endswith("?") and len(b) < 150:
            flush()
            question, answer_parts = b, []
        elif question:
            answer_parts.append(b)
    flush()
    return chunks


def _chunk_whole_page(text: str, meta: dict) -> list[Chunk]:
    """One chunk for the entire cleaned text — for short, single-message pages
    where per-paragraph splitting would fragment a coherent message into
    pieces each individually too short to pass _chunk_paragraph_anchored's
    80-char threshold (found live: RBI Kehta Hai poster pages — the combined
    message is substantive, but each line of it is short). The 80-char bar is
    right for the RBI Master Direction's long legal prose; it is wrong for a
    page whose entire content is one short campaign message.
    """
    text = text.strip()
    if not text:
        return []
    return [Chunk(doc_id=meta["id"], doc_title=meta["title"], authority=meta["authority"],
                  clause_id="full page", text=text, retrieved_at=meta["retrieved_at"])]


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"&nbsp;?", " ", raw)
    return re.sub(r"[ \t]{2,}", " ", raw)


def strip_rbi_kehta_hai_chrome(text: str) -> str:
    """rbikehtahai.rbi.org.in repeats an identical language switcher and a
    sitewide nav menu (every topic title on the site) on every page. Without
    stripping them, a chunk from a manually-saved page here would be dominated
    by ~2KB of shared boilerplate instead of the actual short safety message.
    Guarded to authority == public-awareness by the caller — these markers are
    specific to this one site and are safe no-ops (`in` check fails, text
    unchanged) if they never appear, but there is no reason to run them against
    the regulation/specification/sro-guidance sources at all.

    Right boundary is the nav menu's own first item ("Account Aggregator
    Facility"), not a trailing marker like "Back to Home" — found live: one
    saved page's DOM didn't happen to include "Back to Home" at all, so that
    split silently no-opped and let the entire ~1.6KB nav menu through
    disguised as real content. The nav's first item is present, at a
    consistent position, in every file actually saved from this site.
    """
    if "Urdu" in text:
        text = text.split("Urdu", 1)[1]
    if "Account Aggregator Facility" in text:
        text = text.split("Account Aggregator Facility", 1)[0]
    return text.strip()


def build() -> list[Chunk]:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    chunks: list[Chunk] = []
    for meta in manifest:
        path = CORPUS.parent / meta["path"]
        if meta["kind"] == "markdown":
            chunks += chunk_markdown(path.read_text(errors="ignore"), meta)
        elif meta["kind"] == "html":
            text = strip_html(path.read_text(errors="ignore"))
            if meta.get("shape") == "faq":
                chunks += chunk_faq(text, meta)
            elif meta["authority"] == "public-awareness":
                text = strip_rbi_kehta_hai_chrome(text)
                chunks += _chunk_whole_page(text, meta)
            else:
                chunks += chunk_numbered(text, meta)
        elif meta["kind"] == "pdf":
            import pdfplumber  # imported lazily; only needed if a PDF is in the corpus
            with pdfplumber.open(path) as pdf:
                raw = "\n\n".join((p.extract_text() or "") for p in pdf.pages)
            chunks += chunk_numbered(raw, meta)

    out = CORPUS / "chunks.json"
    out.write_text(json.dumps([asdict(c) for c in chunks], indent=2))
    print(f"{len(chunks)} chunks -> {out}")
    # Worth eyeballing: if one doc produced 3 chunks, chunking failed on it.
    for doc in {c.doc_id for c in chunks}:
        print(f"  {doc}: {sum(1 for c in chunks if c.doc_id == doc)}")
    return chunks


if __name__ == "__main__":
    build()
