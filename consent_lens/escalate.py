"""Compromise escalation — FR-23. Runs FIRST, before the refusal guard and before retrieval.

Some questions are not requests for explanation. "I gave them the OTP, can they take my
money?" is a person who may be in the middle of a fraud. The correct product response is not
a good answer. It is to stop and send them to their bank.

Design rules, from PRD §4.1 and non-negotiable 9:

  - Fires before everything. Speed outranks completeness on this path only.
  - No analysis, no reassurance, no explanation first.
  - Never estimates likelihood and never says the user is safe.
  - Biased toward OVER-triggering. Under-triggering is the dangerous direction here,
    exactly as under-refusal is for the guard (PRD risk 8). A false positive costs a user
    one unnecessary phone call; a false negative costs them an explanation while money moves.

Every false positive gets logged, because an escalation path nobody can tolerate is one
that gets switched off.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Credential = something that authorises a transaction, as opposed to information that
# describes one. The distinction is the whole reason this module is separate from the
# exposure register.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("otp_shared", re.compile(
        r"\b(gave|shared|told|sent|read out|typed|passed on|disclosed)\b[\w\s,'-]{0,30}\b"
        r"(otp|one[\s-]?time[\s-]?password|verification code|auth(entication)? code|sms code)\b"
        r"|\botp\b[\w\s,'-]{0,25}\b(shared|gave|given|sent|told|disclosed)\b", re.I)),

    ("credentials_shared", re.compile(
        r"\b(gave|shared|told|sent|disclosed|handed over)\b[\w\s,'-]{0,30}\b"
        r"(password|pin|upi pin|mpin|cvv|card number|net ?banking (login|credentials|details)|"
        r"user ?id and password|login details)\b", re.I)),

    ("remote_access", re.compile(
        r"\b(anydesk|teamviewer|quick ?support|remote (access|desktop)|screen[\s-]?shar\w+)\b"
        r"[\w\s,'-]{0,40}\b(installed|downloaded|allowed|gave|shared|they asked)\b"
        r"|\b(installed|downloaded)\b[\w\s,'-]{0,20}\b(anydesk|teamviewer)\b", re.I)),

    ("qr_scan_payment", re.compile(
        r"\bqr\b[\w\s,'-]{0,40}\b(scan\w*|clicked)\b[\w\s,'-]{0,60}\b(otp|pin|code|approve|paid)\b"
        r"|\bscan\w*\b[\w\s,'-]{0,20}\bqr\b[\w\s,'-]{0,60}\b(otp|pin|code)\b", re.I)),

    ("unauthorised_debit", re.compile(
        r"\b(money (was |has been )?(debited|withdrawn|taken|gone|missing)|"
        r"unauthoris?ed (transaction|debit)|didn'?t (make|authoris?e) (this|that|the) "
        r"(transaction|payment|debit)|someone (took|withdrew) money)\b", re.I)),

    ("link_clicked_then_credentials", re.compile(
        r"\b(clicked|opened|tapped)\b[\w\s,'-]{0,30}\b(link|sms|message|whatsapp)\b"
        r"[\w\s,'-]{0,60}\b(otp|pin|password|card|logged in|login)\b", re.I)),
]

# Numbers a user should be able to act on immediately.
# VERIFY BEFORE PUBLICATION — safety-critical content must not be stale.
NATIONAL_CYBERCRIME_HELPLINE = "1930"
CYBERCRIME_PORTAL = "cybercrime.gov.in"


@dataclass
class Escalation:
    triggered: bool
    kind: str | None
    matched: str | None
    text: str = ""


TEMPLATE = """Stop and act on this now, before reading anything else.

What you've described involves {what} — that is different from sharing information, because it can authorise a transaction.

1. Call your bank's fraud helpline immediately. Use the number printed on your card or in your bank's own app — not a number from a message or from whoever contacted you.
2. Block the card or freeze the account through your bank's app if you can do it faster yourself.
3. Report it on {portal}, or call {helpline}.

I'm not going to assess how likely a loss is, and I'm not going to tell you it's fine. Your bank can act on the account right now; I can't."""

WHAT = {
    "otp_shared": "a one-time passcode being shared",
    "credentials_shared": "account credentials being shared",
    "remote_access": "someone being given remote access to your device",
    "qr_scan_payment": "a scanned QR code followed by a code or PIN being entered",
    "unauthorised_debit": "money leaving your account without your authorisation",
    "link_clicked_then_credentials": "credentials being entered after following a link",
}


def check(question: str) -> Escalation:
    for kind, pat in PATTERNS:
        m = pat.search(question)
        if m:
            return Escalation(
                triggered=True,
                kind=kind,
                matched=m.group(0),
                text=TEMPLATE.format(
                    what=WHAT[kind],
                    portal=CYBERCRIME_PORTAL,
                    helpline=NATIONAL_CYBERCRIME_HELPLINE,
                ),
            )
    return Escalation(False, None, None)
