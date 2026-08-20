"""Fetch and snapshot the corpus. Every source is stored with its retrieval date.

Citations are only verifiable if we know WHICH version we cited. The RBI Master Direction
is amended; a citation without an as-of date is unverifiable later. That is why this writes
corpus/manifest.json alongside the documents.

Two levels of authority are carried through the whole pipeline and must never be conflated:

    regulation        binding. The RBI Master Direction.
    specification     the technical artefact definition. DEPA / ReBIT.
    sro-guidance      Sahamati. Design guidance, not binding.
    public-awareness  RBI's consumer-education material. Published by the regulator,
                      but it is safety advice, not regulation, and has no clause numbers.

An answer that cites public-awareness material as though it were regulation is a defect,
not a stylistic preference.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

import httpx

from .chunk import strip_html, strip_rbi_kehta_hai_chrome

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
MANUAL = CORPUS / "manual"

SOURCES = [
    {
        "id": "rbi-md-nbfc-aa",
        "title": "RBI Master Direction — NBFC Account Aggregator (Reserve Bank) Directions, 2016",
        "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10598",
        "kind": "html",
        "authority": "regulation",
        # RBI/DNBR/2016-17/46 · issued 02 Sep 2016 · page states last updated 06 Sep 2024.
        # Served as HTML, not PDF — clause extraction is far more reliable than expected.
        # VERIFY: confirm no later consolidated instrument supersedes this before citing it.
        "note": "Para 6 = Consent Architecture (6.3 = consent artefact contents). "
                "Para 7 = Sharing of financial information. Para 10 = Rights of the customer.",
    },
    {
        "id": "depa-consent-artefact",
        "title": "DEPA — Consent Artefact",
        "url": "https://depa.world/learn/consent-artefact",
        "kind": "html",
        "authority": "specification",
    },
    {
        "id": "cdsl-cas-faq",
        "title": "CDSL — Consolidated Account Statement (CAS) FAQ",
        "url": "https://www.cdslindia.com/cas/FAQ.html",
        "kind": "html",
        "authority": "public-awareness",
        "shape": "faq",
        # The only source found specifically covering eCAS/CAS — closes the Q1 gap
        # (entries 4/6: the model could identify eCAS as ungoverned but had nothing
        # citable for what a CAS actually is or its regulatory basis). Cites real
        # SEBI circular CIR/MRD/DP/31/2014 (12 Nov 2014) as the basis for CAS
        # issuance — but this page is CDSL's own FAQ explainer, not the circular
        # text itself, hence public-awareness rather than regulation.
    },
    {
        "id": "sahamati-consent-guidelines",
        "title": "Sahamati — Design Principles for Informed Consent",
        "url": "https://raw.githubusercontent.com/Sahamati/customer-experience-guidelines/main/consent-guidelines.md",
        "kind": "markdown",
        "authority": "sro-guidance",
    },
]

# ---------------------------------------------------------------------------
# Manual sources.
#
# rbikehtahai.rbi.org.in is behind a CAPTCHA and cannot be fetched programmatically.
# That is a finding, not an obstacle: RBI's own consumer-safety material is not
# machine-accessible, which is worth a line in the failure log.
#
# To include one: open the page, save it into corpus/manual/ with any name you
# like, and rerun. Auto-discovered below — not a fixed id list. The first
# attempt at this was a fixed list of guessed URLs and ids, written before
# anyone had seen the real site; none of it matched what was actually there
# once real pages got saved (found live: entry 8's investigation). The real
# site's topics (AEPS, Tokenisation, "limit loss on fraud", ...) aren't
# knowable in advance, and browsers don't save files under a slug id anyway.
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _discover_manual() -> list[dict]:
    """Auto-discover corpus/manual/*.html rather than requiring pre-guessed
    filenames. Skips a file if it has no usable content after the site's
    chrome is stripped (this site sometimes doesn't render real content into
    a static save — worth re-saving, not silently including an empty source)
    or if its content exactly duplicates an earlier file (multiple saves
    landing on the same default page).
    """
    candidates = []
    for path in sorted(MANUAL.glob("*.html")):
        content = path.read_bytes()
        core = strip_rbi_kehta_hai_chrome(strip_html(content.decode("utf-8", errors="ignore")))
        if len(core) < 200:
            print(f"    skip    {path.name} (no usable content after cleanup — re-save it)")
            continue
        suffix = path.stem.replace("RBI Kehta Hai", "").strip(" -!")
        candidates.append((path, content, core, suffix))

    # Longest (most descriptive) filename suffix wins a duplicate-content tie —
    # not first-alphabetically. Found live: the file with no suffix at all
    # ("RBI Kehta Hai !.html", saved before navigating anywhere) sorted first
    # and wrongly won over "RBI Kehta Hai digital arrest.html", which has the
    # SAME content but an actual topic name. First-wins would have produced a
    # citation reading just "RBI Kehta Hai" with no topic — unverifiable in
    # practice even though the underlying content is real.
    candidates.sort(key=lambda c: len(c[3]), reverse=True)

    found = []
    seen_hashes: set[str] = set()
    for path, content, core, suffix in candidates:
        h = hashlib.sha256(core.encode()).hexdigest()[:16]
        if h in seen_hashes:
            print(f"    skip    {path.name} (duplicate content of a better-titled save)")
            continue
        seen_hashes.add(h)
        src = {
            "id": _slugify(path.stem) or "rbi-kehta-hai-home",
            "title": f"RBI Kehta Hai — {suffix}" if suffix else "RBI Kehta Hai",
            "url": "https://rbikehtahai.rbi.org.in/ (CAPTCHA-gated — saved manually)",
            "kind": "html",
            "authority": "public-awareness",
        }
        found.append((src, content, path))
        print(f"    ok      {src['id']} ({len(content):,} bytes, {len(core)} chars usable)")
    return found


def _record(src: dict, content: bytes, path: pathlib.Path, how: str) -> dict:
    return {
        **{k: v for k, v in src.items() if k != "note"},
        "path": str(path.relative_to(CORPUS.parent)),
        "sha256": hashlib.sha256(content).hexdigest()[:16],
        "bytes": len(content),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieval_method": how,
    }


def fetch_all() -> list[dict]:
    CORPUS.mkdir(parents=True, exist_ok=True)
    MANUAL.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for src in SOURCES:
        ext = {"markdown": "md", "html": "html", "pdf": "pdf"}[src["kind"]]
        dest = CORPUS / f"{src['id']}.{ext}"
        print(f"  {src['id']} ...", end=" ", flush=True)
        try:
            r = httpx.get(src["url"], timeout=60, follow_redirects=True,
                          headers={"User-Agent": "consent-lens/0.1 (research prototype)"})
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")
            print("    -> log as a corpus-gap failure; do not silently skip it")
            continue
        dest.write_bytes(r.content)
        manifest.append(_record(src, r.content, dest, "automated"))
        print(f"ok ({len(r.content):,} bytes)")

    print("\n  manual sources (CAPTCHA-gated — save by hand into corpus/manual/):")
    for src, content, path in _discover_manual():
        manifest.append(_record(src, content, path, "manual"))

    (CORPUS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    by_auth: dict[str, int] = {}
    for m in manifest:
        by_auth[m["authority"]] = by_auth.get(m["authority"], 0) + 1
    print(f"\n{len(manifest)} sources -> {CORPUS/'manifest.json'}")
    for a, n in sorted(by_auth.items()):
        print(f"  {a}: {n}")
    return manifest


if __name__ == "__main__":
    m = fetch_all()
    sys.exit(0 if any(x["authority"] == "regulation" for x in m) else 1)
