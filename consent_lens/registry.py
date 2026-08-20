"""Route identification and the framework-gap register.

Two facts this build exists to establish:

  1. Not every way you share financial data is governed. The Account Aggregator
     route carries purpose limitation, expiry, revocability and an audit trail.
     Forwarding an eCAS PDF carries none of them — the statement's *issuance* is
     regulated (CAMS/KFintech are SEBI-regulated RTAs; NSDL/CDSL are depositories),
     but the *onward sharing* is not governed by any consent framework.
     Most citizens cannot tell which one they used. That is the product.

  2. "The system couldn't answer" and "the framework doesn't cover this" are
     different findings. Without a curated register, an empty retrieval is
     indistinguishable from a genuine framework gap, and the system will guess.

Every entry carries its evidence and its verification status. UNVERIFIED entries
must be surfaced to the user as unresolved, never asserted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Route(str, Enum):
    AA = "AA"                      # Account Aggregator — governed
    ECAS = "ECAS"                  # emailed/forwarded consolidated statement
    PDF_UPLOAD = "PDF_UPLOAD"      # statement uploaded to a portal
    CREDENTIAL_SHARING = "CREDENTIAL_SHARING"  # net-banking login handed over
    UNKNOWN = "UNKNOWN"


GOVERNED = {Route.AA}

ROUTE_PATTERNS = [
    (Route.AA, re.compile(r"\b(account aggregator|\baa\b|consent (screen|request|artefact)|"
                          r"finvu|onemoney|anumati|camsfinserv|nadl|saafe|protean)\b", re.I)),
    # "(?:\w+\s+){0,5}" tolerates a bank/entity name inserted between an anchor word
    # ("my"/"the") and "statement" — e.g. "uploaded my ICICI bank statement", "forwarded
    # my HDFC CAS statement". Without it, a real named-bank phrasing breaks the adjacency
    # the pattern otherwise assumes (found live: "uploaded my ICICI bank statement..."
    # classified UNKNOWN instead of PDF_UPLOAD — same shape as entries 2 and 8).
    (Route.ECAS, re.compile(r"\b(e-?cas|consolidated account statement|cams statement|"
                            r"kfintech statement|forwarded (my |the )?(?:\w+\s+){0,5}statement|"
                            r"nsdl statement|cdsl statement)\b", re.I)),
    (Route.PDF_UPLOAD, re.compile(r"\b(upload(ed)? (my |the )?(?:\w+\s+){0,5}(bank )?statement|"
                                  r"sent (them |him |her )?(my )?(pdf|statement))\b", re.I)),
    (Route.CREDENTIAL_SHARING, re.compile(r"\b(net ?banking (password|login|credentials)|"
                                          r"gave (them|him|her) my password|shared my (otp|password))\b", re.I)),
]


@dataclass
class RouteFinding:
    route: Route
    governed: bool
    note: str


def identify_route(text: str) -> RouteFinding:
    for route, pat in ROUTE_PATTERNS:
        if pat.search(text):
            return RouteFinding(
                route=route,
                governed=route in GOVERNED,
                note=_NOTES[route],
            )
    return RouteFinding(Route.UNKNOWN, False, _NOTES[Route.UNKNOWN])


_NOTES = {
    Route.AA: "Account Aggregator route. Governed: purpose-limited, time-bound, "
              "revocable, and recorded in a consent artefact.",
    Route.ECAS: "Consolidated account statement shared by email or file. The statement's "
                "issuance is regulated, but forwarding it is not governed by any consent "
                "framework — no consent artefact, no purpose limitation, no expiry, "
                "no revocation, no audit trail.",
    Route.PDF_UPLOAD: "Statement uploaded directly to a service. No consent artefact "
                      "governs what happens to it afterwards.",
    Route.CREDENTIAL_SHARING: "Credentials shared directly. Outside every consent "
                              "framework, and outside the protections that depend on one.",
    Route.UNKNOWN: "Route not identified from the description. Which route was used "
                   "determines which protections apply — worth establishing first.",
}


class GapCause(str, Enum):
    SPEC_EXCLUDES = "SPEC_EXCLUDES"                    # the specification rules it out
    NO_FIP_IMPLEMENTATION = "NO_FIP_IMPLEMENTATION"    # allowed, but nobody built it
    RULE_ELSEWHERE = "RULE_ELSEWHERE"                  # governed outside this corpus
    UNRESOLVED = "UNRESOLVED"                          # we genuinely do not know which


@dataclass
class Gap:
    topic: str
    patterns: list[str]
    cause: GapCause
    evidence: str
    verified: bool = False
    user_text: str = ""
    _compiled: list[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compiled = [re.compile(p, re.I) for p in self.patterns]

    def matches(self, q: str) -> bool:
        return any(p.search(q) for p in self._compiled)


# Seeded from PRD Appendix B. Nothing here is verified against a primary source yet
# — which is why every entry says so out loud rather than asserting.
REGISTER: list[Gap] = [
    Gap(
        topic="joint accounts",
        # Bidirectional and covers "jointly" as an adverb, not just "joint" as an adjective
        # immediately before the noun — "the account I hold jointly" and "jointly held
        # account" both need to match, not only "joint account" (found live: entry 8, the
        # original narrower pattern missing its own topic paraphrased either way).
        patterns=[r"\bjoint(ly)?\b.{0,30}\b(account|holding|held|hold|own(s|ed)?)\b",
                  r"\baccount\b.{0,30}\bjoint(ly)?\b",
                  r"\baccount .{0,20}(with|and) my (husband|wife|spouse)"],
        cause=GapCause.UNRESOLVED,
        evidence="Reported across secondary sources that no bank supports joint-account "
                 "discovery on AA. Whether that is a specification exclusion or universal "
                 "non-implementation is not established.",
        verified=False,
        user_text="Joint accounts can't currently be linked or shared through AA — as far as "
                  "I can tell, no bank supports it. I should be straight with you about the "
                  "limit of what I know: I can see it doesn't work in practice, but whether "
                  "the rules exclude joint accounts or banks simply haven't built it, I can't "
                  "tell you from these documents.",
    ),
    Gap(
        topic="NRE/NRO accounts",
        patterns=[r"\bnre\b", r"\bnro\b", r"\bnri account"],
        cause=GapCause.UNRESOLVED,
        evidence="Reported as not discoverable via AA. Cause not established.",
        verified=False,
    ),
    Gap(
        topic="post-revocation deletion",
        patterns=[r"(delete|erase|remove).{0,40}(already|after|once).{0,20}(shared|revok)",
                  r"revok.{0,40}delete"],
        cause=GapCause.RULE_ELSEWHERE,
        evidence="Revocation stops future data flow. Whether it compels deletion of data "
                 "already retained may be governed by the DPDP Act rather than the AA "
                 "corpus. To be confirmed against the primary sources.",
        verified=False,
    ),
]


def check_gap_register(question: str) -> Gap | None:
    for gap in REGISTER:
        if gap.matches(question):
            return gap
    return None


# ---------------------------------------------------------------------------
# Exposure register — FR-22
#
# What a shared artefact STRUCTURALLY ENABLES. Capability only.
#
# The hard rule (PRD non-negotiable 9): this may state what an artefact does and does not
# make possible. It may never say the user is safe, and it may never estimate how likely
# a loss is. "No, nobody can touch your money" is an assurance, and this product cannot
# make one — it does not know what else was shared, whether credentials leaked by another
# path, or whether someone is being socially engineered right now.
#
# Anything involving a credential does not belong here at all. It belongs in escalate.py.
# ---------------------------------------------------------------------------


@dataclass
class Exposure:
    artefact: str
    patterns: list[str]
    carries_credentials: bool
    does_not_enable: str
    does_enable: str
    evidence: str
    verified: bool = False
    _compiled: list[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compiled = [re.compile(p, re.I) for p in self.patterns]

    def matches(self, q: str) -> bool:
        return any(p.search(q) for p in self._compiled)


EXPOSURE_REGISTER: list[Exposure] = [
    Exposure(
        artefact="eCAS / consolidated account statement",
        patterns=[r"\be-?cas\b", r"consolidated account statement",
                  r"(mutual fund|mf|portfolio|holding)s? statement"],
        carries_credentials=False,
        does_not_enable="Redeeming, transferring or debiting the account. A redemption has to be "
                        "authenticated with the fund house or platform, and the statement carries "
                        "no credential and no authorisation.",
        does_enable="Complete visibility of what you hold, where, and how much — which makes an "
                    "approach from someone pretending to be your fund house or advisor far more "
                    "convincing.",
        evidence="Author's assessment from domain knowledge. An eCAS is a reporting document "
                 "issued by an RTA or depository; it contains no authentication material.",
        verified=False,
    ),
    Exposure(
        artefact="bank statement PDF",
        patterns=[r"bank statement", r"account statement (pdf|file)", r"uploaded my statement"],
        carries_credentials=False,
        does_not_enable="A debit by itself. Moving money out requires authentication the "
                        "statement does not contain.",
        does_enable="Salary, balance, EMI and spending profiling, and the account number — "
                    "enough to make a targeted approach credible.",
        evidence="Author's assessment from domain knowledge.",
        verified=False,
    ),
    Exposure(
        artefact="Account Aggregator consent",
        patterns=[r"account aggregator", r"\baa\b consent", r"consent (artefact|screen|request)"],
        carries_credentials=False,
        does_not_enable="Any transaction. AA is a data-sharing rail, not a payment rail — a "
                        "consent grants read access to specified data, not the ability to move money.",
        does_enable="Access to the data types named in the consent, for the period it covers.",
        evidence="To verify against the DEPA specification and RBI Master Direction during ingestion.",
        verified=False,
    ),
]


def check_exposure_register(question: str) -> Exposure | None:
    """Capability lookup. Returns None rather than guessing.

    Note what is deliberately absent: OTPs, PINs, passwords and card details have no entry
    here. A question about those is not a question about exposure, it is a question about
    access — and it is routed to escalate.check() before this is ever called.
    """
    for e in EXPOSURE_REGISTER:
        if e.matches(question):
            return e
    return None
