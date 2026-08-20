"""Build a single self-contained HTML page from the recorded transcripts.

Deliberately NOT a live web app: no server, no API key in a browser, nothing to
deploy. It replays recorded runs and says so. The point of the page is the
decision trace — showing the branch where the guard fired is worth more than a
chat box that asks the reader to take the boundary on trust.
"""
from __future__ import annotations

import html
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "index.html"   # docs/ so GitHub Pages can serve it

BADGE = {
    "ANSWERED": ("#1a6b4a", "#e6f4ee", "answered with citation"),
    "REFUSED": ("#8a2846", "#fbe9ee", "refused — advice / adjudication"),
    "ABSTAINED": ("#7a5a1e", "#fbf3e0", "abstained — corpus does not settle it"),
    "AUDIT_FAILED": ("#6b2020", "#fbeaea", "answer discarded — citation audit failed"),
    "ESCALATED": ("#7a1414", "#fae3e3", "escalated — possible compromise, sent to the bank"),
    "ASSURANCE_BLOCKED": ("#6b2020", "#fbeaea", "answer discarded — contained a safety assurance"),
}

CSS = """
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
     color:#1c2430;background:#f7f8fb}
.wrap{max-width:860px;margin:0 auto;padding:48px 24px 96px}
h1{font-size:34px;margin:0 0 6px;letter-spacing:-.02em;color:#1F3352}
.sub{color:#5b6779;margin:0 0 28px;font-size:17px}
.note{background:#fff;border:1px solid #dfe4ec;border-left:3px solid #2E5A87;
      padding:14px 18px;border-radius:6px;margin:0 0 34px;font-size:14.5px;color:#41506a}
.q{background:#fff;border:1px solid #dfe4ec;border-radius:10px;margin:0 0 22px;overflow:hidden}
.q header{padding:18px 22px 14px;border-bottom:1px solid #eef1f6}
.qt{font-weight:600;font-size:17px;margin:0 0 10px}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px}
.proves{font-size:13.5px;color:#6b7688;margin:10px 0 0;font-style:italic}
.a{padding:18px 22px;font-size:16px}
.cite{font-size:13px;color:#5b6779;border-left:2px solid #c3cedd;padding-left:12px;margin-top:12px}
details{border-top:1px solid #eef1f6;background:#fbfcfe}
summary{padding:12px 22px;cursor:pointer;font-size:13.5px;color:#2E5A87;font-weight:600;
        user-select:none}
.trace{padding:4px 22px 20px;font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}
.step{padding:8px 12px;margin:6px 0;border-radius:5px;background:#fff;border:1px solid #e6eaf1}
.step b{color:#1F3352}
.k{color:#8a2846}
footer{margin-top:44px;font-size:13.5px;color:#6b7688;border-top:1px solid #dfe4ec;padding-top:20px}
"""


def esc(x) -> str:
    return html.escape(str(x))


def render_step(s: dict) -> str:
    name = s.get("step", "?")
    if name == "guard.classify":
        v = "refused" if s.get("refused") else "passed to agent"
        m = f' matched <span class="k">{esc(s["matched"])}</span>' if s.get("matched") else ""
        return f'<div class="step"><b>[CODE] guard.classify</b> → {esc(s.get("intent"))} — {v}{m}</div>'
    if name == "escalate.check":
        v = "TRIGGERED — escalate, do not answer" if s.get("triggered") else "clear"
        mm = f' matched <span class="k">{esc(s["matched"])}</span>' if s.get("matched") else ""
        return f'<div class="step"><b>[CODE] escalate.check</b> → {v}{mm}</div>'
    if name == "guard.assurance":
        v = "passed" if s.get("passed") else f'FAILED — {esc(s.get("phrases"))}'
        return f'<div class="step"><b>[CODE] guard.assurance</b> → {v}</div>'
    if name == "guard.audit":
        v = "passed" if s.get("passed") else "FAILED — answer discarded"
        return f'<div class="step"><b>[CODE] guard.audit</b> → {v}</div>'
    if name == "tool":
        out = json.dumps(s.get("output", {}), default=str)
        if len(out) > 320:
            out = out[:320] + " …"
        return (f'<div class="step"><b>[AGENT] {esc(s.get("tool"))}</b>'
                f'({esc(json.dumps(s.get("input", {}), default=str)[:160])})<br>→ {esc(out)}</div>')
    if name == "abstain":
        return f'<div class="step"><b>[AGENT] abstain</b> → {esc(s.get("reason"))}</div>'
    return f'<div class="step"><b>{esc(name)}</b> {esc(json.dumps({k: v for k, v in s.items() if k != "step"}, default=str)[:240])}</div>'


def main() -> None:
    data = json.loads((HERE / "transcripts.json").read_text())
    blocks = []
    for t in data:
        colour, bg, label = BADGE.get(t["outcome"], ("#444", "#eee", t["outcome"]))
        cites = "".join(f'<div class="cite">— {esc(c)}</div>' for c in t.get("citations", []))
        steps = "".join(render_step(s) for s in t.get("trace", []))
        blocks.append(f"""
<div class="q">
  <header>
    <p class="qt">{esc(t['question'])}</p>
    <span class="badge" style="color:{colour};background:{bg}">{esc(label)}</span>
    <p class="proves">{esc(t['proves'])}</p>
  </header>
  <div class="a">{esc(t['text']).replace(chr(10), '<br>')}{cites}</div>
  <details><summary>Show decision trace</summary><div class="trace">{steps}</div></details>
</div>""")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consent Lens — recorded runs</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Consent Lens</h1>
<p class="sub">What did I share, and what protections do I actually have?</p>
<div class="note">
<strong>These are recorded runs, not a live demo.</strong> Each answer is grounded in the
published DEPA specification and RBI Master Direction, and carries the clause it came from.
Consent Lens explains what the documents say — it never advises whether to consent, and never
assesses whether an organisation is trustworthy. That boundary is enforced in code before the
question reaches the model. Open a decision trace to see the branch.
</div>
{''.join(blocks)}
<footer>
Built as a three-day probe of whether comprehension, not plumbing, is the bottleneck in
India's Account Aggregator framework. The failure log is in the repository and is not
tidied — the failures are the finding.
</footer>
</div></body></html>""")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
