"""Ask Consent Lens a question.

    python -m consent_lens.cli "what did I share if I forwarded my eCAS?"
    python -m consent_lens.cli --trace "should I approve this?"
    python -m consent_lens.cli            # interactive
"""
from __future__ import annotations

import json
import sys

from .agent import ConsentLens

BANNER = """Consent Lens — explains what India's Account Aggregator consent documents say.
It does not advise, does not assess organisations, and does not interpret your finances.
Ctrl-C to exit.
"""


def _show(r, show_trace: bool) -> None:
    print(f"\n[{r.outcome}]\n{r.text}")
    for c in r.citations:
        print(f"   — {c}")
    if show_trace:
        print("\n--- decision trace " + "-" * 40)
        for step in r.trace:
            print(json.dumps(step, default=str)[:400])
        print("-" * 59)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    show_trace = "--trace" in args
    args = [a for a in args if a != "--trace"]

    lens = ConsentLens()
    if args:
        _show(lens.ask(" ".join(args)), show_trace)
        return

    print(BANNER)
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if q:
            _show(lens.ask(q), show_trace)


if __name__ == "__main__":
    main()
