"""The refusal boundary — enforced in code, before generation.

This is the product, not a safety wrapper around it. Two mechanisms:

  1. classify()   runs BEFORE retrieval. An advice or adjudication question never
                  reaches the generator as a question to answer. A model that is
                  asked to "please refuse advice questions" can be argued out of it;
                  a branch in a function cannot.

  2. audit_claims()  runs AFTER generation. Every factual sentence must map to a
                  retrieved citation OR a known precedent, or the answer is
                  discarded and we abstain.

Both are deliberately boring and readable. That is the point — the mechanism has
to be demonstrable, not merely claimed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    ADVICE = "ADVICE"                    # "should I approve this?"
    ADJUDICATION = "ADJUDICATION"        # "is this lender trustworthy?"
    PERSONAL_FINANCE = "PERSONAL_FINANCE"  # "can I afford this loan?"
    ANSWERABLE = "ANSWERABLE"


# Ordered: first match wins. Kept as explicit patterns so the boundary is auditable.
PATTERNS: list[tuple[Intent, re.Pattern]] = [
    (Intent.ADVICE, re.compile(
        r"\b(should i|shall i|do you recommend|would you (approve|consent|sign)|"
        r"(is|was) (it|this|that) a (good|bad|wise|smart|poor|terrible|sensible) "
        r"(idea|move|call|decision|thing to do)|"
        r"is it (wise|smart|sensible)|what would you do|advise me|"
        r"is it ok(ay)? (to|for me)|am i right to|did i do the right thing)\b", re.I)),
    (Intent.ADJUDICATION, re.compile(
        # entity may be several words ("that advisory service", "this NBFC lender",
        # or a named entity like "Perfios" / "NSDL AA" with no article at all)
        r"\b((is|are|was|were)\s+(?:(?:this|that|the|these|those|they)\s+)?[\w\s'-]{0,40}?\b"
        r"(safe|trustworthy|trusted|legit|legitimate|genuine|reliable|reputable|"
        r"a scam|scam|fraud|fraudulent|dodgy|risky)\b|"
        r"can i trust|is it safe to|how safe (is|are)|"
        r"which (lender|app|aa|account aggregator|advisor|adviser) is (best|better|safest)|"
        r"rate (this|that|them))", re.I)),
    (Intent.PERSONAL_FINANCE, re.compile(
        r"\b(can i afford|should i invest|is my portfolio|how much should i|"
        r"will this (affect|hurt|improve) my (credit|cibil|score)|"
        r"what will happen to my (money|savings|returns))\b", re.I)),
]

REFUSAL = {
    Intent.ADVICE:
        "I can't tell you whether to approve or refuse. I only explain what the "
        "consent documents say — the decision is yours.",
    Intent.ADJUDICATION:
        "I can't assess whether an organisation is safe or trustworthy. I only "
        "explain what the consent documents say. For whether an entity is "
        "regulated, check the relevant regulator's register directly.",
    Intent.PERSONAL_FINANCE:
        "I can't interpret your personal finances. I only explain what the consent "
        "documents say about data sharing.",
}

# Questions we refuse often contain an answerable factual part. Refusing and then
# stranding the user is a worse product than refusing and then helping.
REFORMULATE = re.compile(
    r"\b(consent|data|share|shared|sharing|revoke|delete|retain|retention|"
    r"expiry|purpose|account aggregator|\baa\b|ecas)\b", re.I)


@dataclass
class Classification:
    intent: Intent
    matched: str | None          # the literal text that tripped the guard
    reformulate: bool            # is there an answerable factual sub-question?

    @property
    def refused(self) -> bool:
        return self.intent is not Intent.ANSWERABLE


def classify(question: str) -> Classification:
    for intent, pat in PATTERNS:
        m = pat.search(question)
        if m:
            return Classification(intent, m.group(0), bool(REFORMULATE.search(question)))
    return Classification(Intent.ANSWERABLE, None, False)


# --- post-generation audit -------------------------------------------------

HEDGES = re.compile(
    r"^\s*(i can't|i cannot|i don't|the (documents?|specification|corpus) (do(es)? not|don't)|"
    r"this isn't|that's your call|whether)", re.I)


# Non-negotiable 9: the product may state capability, never safety. This catches the
# phrasings that slip in when a model tries to be reassuring.
ASSURANCE = re.compile(
    r"\b(you('| a)?re (safe|fine|protected|in the clear)|"
    r"(there|that)('s| is) no risk|nothing to worry about|"
    r"no one can (access|touch|take|withdraw)|nobody can (access|touch|take|withdraw)|"
    r"(completely|perfectly|totally) (safe|secure)|"
    r"you have nothing to (worry|fear)|rest assured|don'?t worry|"
    r"(unlikely|impossible) that (anyone|someone|they) (could|can|will))\b", re.I)


def assurance_check(answer: str) -> tuple[bool, list[str]]:
    """Returns (ok, offending_phrases). An answer containing assurance is discarded."""
    hits = [m.group(0) for m in ASSURANCE.finditer(answer)]
    return (not hits), hits


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower()))


def audit_claims(text: str, citations: list[str], precedents: list[str],
                  overlap_threshold: float = 0.4
                  ) -> tuple[bool, list[str], list[str]]:
    """Every factual sentence needs a citation behind it, or a known precedent —
    common sense within the guardrails, not just citation or nothing.

    A factual sentence passes if EITHER `citations` is non-empty (audit()'s
    original coarse rule — kept as-is, not redesigned to per-sentence here) OR
    the sentence substantially restates a known precedent — a Gap.user_text, a
    route's structural note, or an Exposure register entry this conversation
    actually retrieved — measured by word-overlap coverage of the SENTENCE by
    the precedent, not the reverse, so a sentence introducing a new claim
    alongside a real paraphrase still fails. Precedent-only passes are returned
    separately (`precedent_backed`) so the caller can visibly label them: "a
    bank statement carries no login credentials" is true and doesn't need a
    regulator to have written it down, but the answer must say so honestly
    rather than dressing it up as a citation it doesn't have. Found live: route
    identification and the exposure register (both self-authored structural
    reasoning — which framework governs this route, does an eCAS or bank
    statement carry credentials?) were never corpus-cited, so EVERY
    route/exposure-driven answer was structurally blocked before this — not a
    retrieval gap, an architecture gap. This is also what replaced
    audit_abstain(): abstain's citation-free text needed exactly this same
    precedent-or-nothing check (entry 7, gap register only); generalizing it
    here extends the same mechanism to route/exposure reasoning and to
    answer()'s citation-bearing path.

    Default threshold is 0.4, not the 0.6 the gap-register case (entry 7) was
    tuned against — calibrated empirically, twice. First finding: a model
    restating structural reasoning in flowing prose (not copying register
    phrasing near-verbatim, the way it tends to with Gap.user_text) naturally
    shares less literal vocabulary with any ONE precedent, even when correct —
    a real PDF-upload case scored 0.20/0.31 against its two precedents
    (a route note and an exposure register entry) taken separately. Second
    finding: a synthesized sentence often draws on BOTH tools called that
    turn at once ("uploaded, so ungoverned, and it doesn't carry credentials
    either") — hence `covered_by_precedent` checks the UNION of all
    precedents' vocabulary, not the max of any single one; that same sentence
    scores 0.43 against the union. 0.4 is the highest threshold that passes
    both real motivating cases while still rejecting every adversarial one
    tested, including a sentence that shares real vocabulary with a precedent
    but asserts something false ("...is completely safe from any kind of
    misuse") — that still fails, both on coverage and on assurance_check() as
    a backstop; and margin was checked, not assumed — 0.35 and 0.3 also pass
    the same battery, so 0.4 isn't a threshold sitting right at the edge of
    the adversarial cases it needs to reject.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    factual = [s for s in sentences if not HEDGES.match(s) and len(s.split()) > 4]
    precedent_words = [_words(p) for p in precedents if p]
    # Union, not per-precedent max: a sentence combining a route note and an exposure
    # register claim into one synthesized statement ("uploaded, so ungoverned, and it
    # doesn't carry credentials either") draws on BOTH tools called this turn — found
    # live: entry 11's real case scored 0.20/0.31 against either precedent alone but
    # 0.43 against their union. Still bounded: the pool is only what tools actually
    # returned this conversation, never the whole corpus.
    all_precedent_words = set().union(*precedent_words) if precedent_words else set()

    def covered_by_precedent(sentence: str) -> bool:
        sw = _words(sentence)
        return bool(sw) and len(sw & all_precedent_words) / len(sw) >= overlap_threshold

    unsupported, precedent_backed = [], []
    for s in factual:
        if citations:
            continue
        if covered_by_precedent(s):
            precedent_backed.append(s)
        else:
            unsupported.append(s)
    return (not unsupported), unsupported, precedent_backed
