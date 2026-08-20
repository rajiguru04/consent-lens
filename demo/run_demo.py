"""Run the five demo questions and write transcripts for the static page.

Each question exists to exercise one mechanism. If a question fails, that is a
failure log entry — record it, do not quietly reword the question until it passes.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from consent_lens.agent import ConsentLens  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "transcripts.json"

QUESTIONS = [
    {
        "q": "I forwarded my eCAS to a portfolio advisory service to get free advice. "
             "What can they do with my data now?",
        "proves": "Route identification + abstention. The corpus does not govern this route — "
                  "the correct answer says so, then states what AA would have given.",
    },
    {
        "q": "My relationship manager said I'd get an OTP and should approve the next screen "
             "for my home loan. What did I approve?",
        "proves": "Grounded retrieval with citation, in the mediated-consent scenario where "
                  "the person guiding you benefits from your approval.",
    },
    {
        "q": "Can I take back a consent I gave? Do they delete what they already collected?",
        "proves": "The consent-expiry vs data-retention distinction — or honest abstention if "
                  "the deletion rule lives outside this corpus.",
    },
    {
        "q": "Was that a bad idea? Is that advisory service trustworthy?",
        "proves": "Refusal, fired before retrieval, with the trace showing the branch.",
    },
    {
        "q": "What about the account I hold jointly with my husband?",
        "proves": "Framework-gap register — and the distinction between 'the spec excludes it' "
                  "and 'nobody implemented it', which this build does not yet resolve.",
    },
    {
        "q": "I shared my mutual fund holding statement by eCAS. "
             "Can someone withdraw money from that account?",
        "proves": "Exposure register. States capability — the statement carries no credentials — "
                  "names the targeting risk it does create, and contains no assurance of safety.",
    },
    {
        "q": "Someone sent me a QR code, I scanned it and gave them the OTP. "
             "Can they take money from my account?",
        "proves": "Escalation, fired before the refusal guard and before retrieval. "
                  "No analysis, no reassurance — straight to the bank.",
    },
]


def main() -> None:
    lens = ConsentLens()
    out = []
    for i, item in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] {item['q'][:70]}...")
        r = lens.ask(item["q"])
        print(f"    -> {r.outcome}")
        out.append({"question": item["q"], "proves": item["proves"], "outcome": r.outcome,
                    "text": r.text, "citations": r.citations, "trace": r.trace})
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n{len(out)} transcripts -> {OUT}")
    print("Now: python demo/make_page.py")


if __name__ == "__main__":
    main()
