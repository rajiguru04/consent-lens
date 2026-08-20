"""The agentic layer, with deterministic guards on both ends.

    question
      -> [CODE]  escalate.check()      FIRST, unconditionally. A credential already
                                       shared is not a question to answer.
      -> [CODE]  guard.classify()      pre-generation. Refuses without ever handing
                                       the evaluative question to the model.
      -> [AGENT] tool-calling loop     identify_route / retrieve_clauses /
                                       check_gap_register / check_exposure_register
                                       -> answer | abstain
      -> [CODE]  guard.audit()         every factual sentence needs a citation.
      -> [CODE]  guard.assurance()     no answer may tell anyone they are safe.

Precedence is strict: escalation > refusal > answer.

The split is the design: the guard is deterministic, the reasoning is agentic.
An agent that can be talked out of refusing is not a guard.

Every step appends to a trace. The trace is the demo — a claim that a boundary
is "enforced in code" is worth nothing next to a transcript showing the branch.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from dotenv import load_dotenv

from . import escalate
from .guard import Intent, REFUSAL, assurance_check, audit, audit_abstain, classify
from .index import Index
from .registry import check_exposure_register, check_gap_register, identify_route

load_dotenv()


def _cites_clause(citation_text: str, clause_id: str) -> bool:
    """Does citation_text plausibly refer to clause_id?

    Matched on the clause number itself, not the full clause_id or the exact
    Chunk.citation() string, so the model can phrase a citation differently
    ("clause 6.4" vs "cl. 6.4") without being falsely rejected. Word-boundary
    matched, not plain substring: a fabricated "cl. 16.4" must not false-pass
    against a real "cl. 6.4" just because "6.4" occurs inside "16.4".
    """
    core = re.sub(r"^(cl\.|para)\s*", "", clause_id, flags=re.I).strip()
    if not core:
        return False
    return bool(re.search(r"\b" + re.escape(core) + r"\b", citation_text))


TRACES = pathlib.Path(__file__).resolve().parent.parent / "logs" / "traces"
MODEL = os.environ.get("CONSENT_LENS_MODEL", "claude-sonnet-4-5")

SYSTEM = """You are Consent Lens. You explain what India's Account Aggregator consent \
documents say. You have three hard limits:

1. You never advise. You do not say whether someone should consent, approve, or refuse.
2. You never adjudicate. You do not assess whether an organisation is safe or trustworthy.
3. You never assert anything that is not in the clauses returned by retrieve_clauses.

EVERY turn must call exactly one tool. Never reply with plain text, even a partial thought \
or a hedge — a plain-text reply is discarded and treated as a failure to answer. If you are \
not ready to answer or abstain yet, call another tool (identify_route, retrieve_clauses, \
check_gap_register, check_exposure_register) to move the question forward.

Only retrieve_clauses returns a citation. identify_route, check_gap_register and \
check_exposure_register inform your reasoning about routes, gaps and capability, but their \
output is NOT a citation and must never be passed as one to answer's citations argument — \
that field only ever takes citation strings that came from retrieve_clauses. If your answer \
needs to say what a document states (including "what AA would have given" as a comparison \
point for an ungoverned route like eCAS), call retrieve_clauses for that half of the answer \
before calling answer — do not rely on identify_route or check_exposure_register alone to \
support a claim about what a regulation or specification says.

Work in this order:
- If the question describes HOW data was shared, call identify_route first. Which route \
was used determines which protections apply, and users usually do not know which they used.
- Call check_gap_register for anything that may be outside the framework.
- Call check_exposure_register when asked what someone could DO with data that was shared. Report only what the register says an artefact structurally enables or does not enable.
- Call retrieve_clauses for anything the corpus should cover, and for any comparison point \
you plan to state as fact.
- Then call EITHER answer (with citations) OR abstain. Never both.

abstain's text may only explain why the corpus doesn't settle the question — it must never \
assert what a document says. Any factual claim, however well-hedged, belongs in answer with \
a real citation, not in abstain's free-text field.

NEVER tell anyone they are safe. You may state that an artefact carries no credentials and therefore does not by itself enable a transaction. You may NOT say "you're safe", "there's no risk", "nobody can touch your money", or estimate how likely a loss is — you do not know what else was shared or what is happening to this person right now. State capability; leave the verdict to them.

Answers are at most 3 sentences and use no unexplained jargon. If a specification term \
appears, gloss it in plain words. If retrieval returns nothing adequate, abstain — do not \
assemble a plausible answer from general knowledge. Saying "these documents don't settle \
that" is a correct and valuable outcome, not a failure."""

TOOLS = [
    {
        "name": "identify_route",
        "description": "Determine how financial data was shared (Account Aggregator, eCAS "
                       "forward, PDF upload, credential sharing) and whether that route is "
                       "governed by a consent framework.",
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string",
                                           "description": "The user's description of what they did"}},
            "required": ["description"],
        },
    },
    {
        "name": "retrieve_clauses",
        "description": "Retrieve clauses from the DEPA specification and RBI Master Direction "
                       "corpus. Returns nothing if the corpus does not address the query.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "check_gap_register",
        "description": "Check whether the question concerns a known gap in the framework or "
                       "its implementations, and what is known about the cause.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "check_exposure_register",
        "description": "Look up what a shared artefact structurally enables and does not enable "
                       "(does an eCAS carry credentials? does an AA consent permit a debit?). "
                       "Capability only — it never reports whether someone is safe.",
        "input_schema": {
            "type": "object",
            "properties": {"artefact": {"type": "string",
                                        "description": "What the user says they shared"}},
            "required": ["artefact"],
        },
    },
    {
        "name": "answer",
        "description": "Give the final answer. Requires at least one citation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "At most 3 sentences, plain language"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text", "citations"],
        },
    },
    {
        "name": "abstain",
        "description": "State that the corpus does not settle this, and why.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason_code": {
                    "type": "string",
                    "enum": ["NOT_IN_CORPUS", "ROUTE_NOT_GOVERNED", "SPEC_EXCLUDES",
                             "NO_FIP_IMPLEMENTATION", "RULE_ELSEWHERE", "UNRESOLVED"],
                },
                "text": {"type": "string"},
            },
            "required": ["reason_code", "text"],
        },
    },
]


@dataclass
class Result:
    question: str
    outcome: str  # ESCALATED | REFUSED | ANSWERED | ABSTAINED | AUDIT_FAILED | ASSURANCE_BLOCKED
    text: str
    citations: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)

    def render(self) -> str:
        out = [self.text]
        for c in self.citations:
            out.append(f"  — {c}")
        return "\n".join(out)


class ConsentLens:
    def __init__(self, index: Index | None = None):
        self.index = index or Index.load()
        from anthropic import Anthropic
        self.client = Anthropic()

    # --- tools ----------------------------------------------------------
    def _run_tool(self, name: str, args: dict, trace: list[dict], cites: list[str],
                  clause_ids: list[str], gap_texts: list[str], question: str):
        if name == "identify_route":
            f = identify_route(args["description"])
            out = {"route": f.route.value, "governed": f.governed, "note": f.note}
        elif name == "retrieve_clauses":
            hits = self.index.search(args["query"], k=5)
            out = {"clauses": [
                {"clause_id": c.clause_id, "document": c.doc_title, "authority": c.authority,
                 "text": c.text[:1200], "score": round(s, 3), "citation": c.citation()}
                for c, s in hits]}
            cites.extend(c.citation() for c, _ in hits)
            clause_ids.extend(c.clause_id for c, _ in hits)
        elif name == "check_exposure_register":
            # Falls back to the original question because the register's regex patterns are
            # a fixed vocabulary, but `args["artefact"]` is free-form model paraphrase that
            # doesn't reliably hit them run to run (found live: entry 8, same defect shape
            # in check_gap_register below).
            e = check_exposure_register(args["artefact"]) or check_exposure_register(question)
            out = ({"found": False} if not e else
                   {"found": True, "artefact": e.artefact,
                    "carries_credentials": e.carries_credentials,
                    "does_not_enable": e.does_not_enable, "does_enable": e.does_enable,
                    "evidence": e.evidence, "verified": e.verified,
                    "reminder": "State capability only. Never assert the user is safe."})
        elif name == "check_gap_register":
            # See entry 8: the model's own topic paraphrase ("jointly held account") can miss
            # a register entry ("joint account") that the original question would have hit.
            g = check_gap_register(args["topic"]) or check_gap_register(question)
            out = ({"found": False} if not g else
                   {"found": True, "topic": g.topic, "cause": g.cause.value,
                    "evidence": g.evidence, "verified": g.verified,
                    "suggested_wording": g.user_text or None})
            if g and g.user_text:
                gap_texts.append(g.user_text)
        else:
            out = {}
        trace.append({"step": "tool", "tool": name, "input": args, "output": out})
        return out

    # --- main -----------------------------------------------------------
    def ask(self, question: str, max_turns: int = 6) -> Result:
        trace: list[dict] = []

        # 0. compromise escalation — FR-23. Runs before everything, including the guard.
        #    A person who has already given away a credential does not need an explanation.
        esc = escalate.check(question)
        trace.append({"step": "escalate.check", "triggered": esc.triggered,
                      "kind": esc.kind, "matched": esc.matched})
        if esc.triggered:
            return self._save(Result(question, "ESCALATED", esc.text, [], trace))

        # 1. deterministic gate, BEFORE the model sees anything
        cls = classify(question)
        trace.append({"step": "guard.classify", "intent": cls.intent.value,
                      "matched": cls.matched, "refused": cls.refused})
        if cls.refused:
            text = REFUSAL[cls.intent]
            if cls.reformulate:
                sub = self.ask(_factual_part(question))
                if sub.outcome == "ANSWERED":
                    text += "\n\n" + sub.text
                    trace.append({"step": "reformulated", "sub_trace": sub.trace})
                    return self._save(Result(question, "REFUSED", text, sub.citations, trace))
            return self._save(Result(question, "REFUSED", text, [], trace))

        # 2. agentic tool loop
        messages = [{"role": "user", "content": question}]
        citations: list[str] = []
        retrieved_clause_ids: list[str] = []
        gap_texts: list[str] = []
        for _ in range(max_turns):
            resp = self.client.messages.create(
                model=MODEL, max_tokens=1200, system=SYSTEM, tools=TOOLS, messages=messages)
            messages.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                trace.append({"step": "no_tool_call", "note": "model returned prose; forcing abstain"})
                return self._save(Result(question, "ABSTAINED",
                                         "I can't answer that from these documents.", [], trace))

            results = []
            for call in calls:
                if call.name == "answer":
                    text = call.input["text"]
                    model_cites = call.input.get("citations", [])
                    # Membership check: a citation the model wrote itself is only trustworthy
                    # if it's traceable to a clause_id retrieve_clauses actually returned this
                    # conversation. Matched by clause_id substring, not exact string, so the
                    # model can phrase the citation differently from Chunk.citation() without
                    # being falsely rejected. This is what actually enforces "no invented
                    # clause numbers" (failure log 0b) — audit() alone only checks non-emptiness.
                    unverified = [c for c in model_cites
                                  if not any(_cites_clause(c, cid) for cid in retrieved_clause_ids)]
                    cites = model_cites or citations
                    ok, bad = audit(text, cites)
                    trace.append({"step": "guard.audit", "passed": ok, "unsupported": bad,
                                  "unverified_citations": unverified})
                    if not ok or unverified:
                        return self._save(Result(
                            question, "AUDIT_FAILED",
                            "I can't answer that without pointing you to the clause it comes from.",
                            [], trace))
                    safe_ok, phrases = assurance_check(text)
                    trace.append({"step": "guard.assurance", "passed": safe_ok,
                                  "phrases": phrases})
                    if not safe_ok:
                        return self._save(Result(
                            question, "ASSURANCE_BLOCKED",
                            "I can tell you what a document or an artefact does and doesn't make "
                            "possible, but I can't tell you that you're safe — I don't know what "
                            "else was shared. If you're worried, your bank or fund house can put "
                            "alerts on the account today.",
                            [], trace))
                    return self._save(Result(question, "ANSWERED", text, cites, trace))
                if call.name == "abstain":
                    reason = call.input["reason_code"]
                    text = call.input["text"]
                    # abstain carries no citations by design — so a factual sentence is only
                    # allowed through if it substantially restates a human-vetted precedent
                    # (a Gap.user_text this conversation actually retrieved via
                    # check_gap_register), not a fresh, uncited claim. A model that wants to
                    # state something new as fact should retrieve and cite it via answer(),
                    # not smuggle it into abstain's free-text field (found live: entry 5, an
                    # uncited paraphrase of cl. 6.3 inside an abstain call). The precedent
                    # exemption exists because the stricter rule alone also discarded a
                    # CORRECT gap-register paraphrase (entry 7) — audit_abstain() lets that
                    # through via word-overlap against gap_texts, still rejects anything else.
                    ok, bad = audit_abstain(text, gap_texts)
                    safe_ok, phrases = assurance_check(text)
                    trace.append({"step": "abstain", "reason": reason, "audit_passed": ok,
                                  "unsupported": bad, "assurance_passed": safe_ok,
                                  "assurance_phrases": phrases})
                    if not ok or not safe_ok:
                        text = f"I can't answer that from these documents. ({reason})"
                    return self._save(Result(question, "ABSTAINED", text, [], trace))
                out = self._run_tool(call.name, call.input, trace, citations,
                                     retrieved_clause_ids, gap_texts, question)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})

        trace.append({"step": "max_turns"})
        return self._save(Result(question, "ABSTAINED",
                                 "I couldn't resolve that from these documents.", [], trace))

    def _save(self, r: Result) -> Result:
        TRACES.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        (TRACES / f"{stamp}.json").write_text(json.dumps({
            "question": r.question, "outcome": r.outcome, "text": r.text,
            "citations": r.citations, "trace": r.trace,
        }, indent=2, default=str))
        return r


def _factual_part(q: str) -> str:
    """Strip the evaluative clause so the factual sub-question can be answered.

    Crude on purpose. Over-stripping produces a worse answer; under-stripping would
    hand the model the evaluative question, which is the thing we must not do.
    """
    import re
    parts = re.split(r"[.?!]|\b(?:and|but|also)\b", q)
    from .guard import classify as _c
    keep = [p.strip() for p in parts if p and p.strip() and not _c(p).refused]
    return " ".join(keep) or "What does this consent cover and for how long?"
