"""The refusal boundary — enforced in code, before generation.

This is the product, not a safety wrapper around it. Two mechanisms:

  1. classify()   runs BEFORE retrieval. An advice or adjudication question never
                  reaches the generator as a question to answer. A model that is
                  asked to "please refuse advice questions" can be argued out of it;
                  a branch in a function cannot.

  2. audit()      runs AFTER generation. Every factual sentence must map to a
                  retrieved citation, or the answer is discarded and we abstain.

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


def audit(answer: str, citations: list[str]) -> tuple[bool, list[str]]:
    """Every factual sentence needs a citation behind the answer.

    Crude by design: it checks that an answer making claims is not citation-free.
    Refusals and abstentions are exempt — a statement about the system's own
    boundaries is not a claim about the corpus.

    Returns (ok, offending_sentences).
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]
    factual = [s for s in sentences if not HEDGES.match(s) and len(s.split()) > 4]
    if factual and not citations:
        return False, factual
    return True, []


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower()))


def audit_abstain(text: str, precedents: list[str], overlap_threshold: float = 0.6
                   ) -> tuple[bool, list[str]]:
    """Like audit(), but for abstain's citation-free text.

    abstain never carries a citation, so by audit()'s own rule every factual sentence
    in it would fail. That's the right default (found live: entry 5, an uncited
    paraphrase of a clause smuggled into an abstain call) — but it also blocked a
    LEGITIMATE case: the gap register's pre-written, human-vetted `Gap.user_text`,
    handed to the model as `suggested_wording` specifically so it can be used (found
    live: entry 7, a correct joint-accounts abstain discarded anyway because the model
    paraphrased that precedent instead of copying it verbatim).

    So: a factual sentence is allowed through only if it substantially restates a
    known precedent (a Gap.user_text this conversation actually retrieved), measured
    by word overlap rather than exact match so paraphrasing doesn't falsely fail.
    Threshold is deliberately high and the overlap is measured as coverage of the
    SENTENCE by the precedent, not the reverse — a sentence introducing new claims
    alongside a real paraphrase should still fail, since letting a fabricated claim
    ride along with a legitimate one is worse than over-rejecting a fine paraphrase.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    factual = [s for s in sentences if not HEDGES.match(s) and len(s.split()) > 4]
    precedent_words = [_words(p) for p in precedents if p]

    def covered(sentence: str) -> bool:
        sw = _words(sentence)
        return bool(sw) and any(
            pw and len(sw & pw) / len(sw) >= overlap_threshold for pw in precedent_words)

    bad = [s for s in factual if not covered(s)]
    return (not bad), bad
