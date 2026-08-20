# Consent Lens

**What did I share, and what protections do I actually have?**

A retrieval-grounded assistant that answers plain-language questions about financial-data
sharing in India, using only the published DEPA specification and the RBI Master Direction,
and citing the clause every answer came from.

It explains. **It never advises, and it never adjudicates.** That boundary is enforced in
code before the question reaches the model — not requested in a prompt.

---

## Why

India's Account Aggregator framework works. The pipe carries volume: 100M+ cumulative
consents, hundreds of institutions. What does not work is a citizen's understanding of what
they agreed to.

This project started with a specific failure. I have 28 years in financial services and I
have built platforms that move regulated financial data. After a home-loan application and a
"free portfolio review", I could not answer three questions about my own data: **what did I
share, how will it be used, and can I delete it?**

Digging further, I found something worse than not understanding the consent screen: I had
not used a consent screen at all. My data had gone via the **eCAS route** — a consolidated
account statement, forwarded. The statement's *issuance* is regulated. The *onward sharing*
is not: no consent artefact, no purpose limitation, no expiry, no revocation, no audit trail.

**I could not tell a governed rail from an ungoverned one.** That is what this answers.

## What it does

| Question | What it exercises |
|---|---|
| *"I forwarded my eCAS for free portfolio advice. What can they do with it now?"* | Identifies the route, recognises the corpus does not govern it, says so, then states what AA would have given — cited |
| *"My RM said I'd get an OTP and should approve the next screen. What did I approve?"* | Grounded retrieval with a verifiable citation |
| *"Can I take it back? Do they delete what they already have?"* | The consent-expiry vs data-retention distinction — or honest abstention if the rule lives outside this corpus |
| *"Was that a bad idea? Is that service trustworthy?"* | **Refused**, before retrieval, with the trace showing the branch |
| *"What about my joint account?"* | Framework gap — and the unresolved distinction between *the spec excludes it* and *nobody implemented it* |
| *"I shared my MF holding statement by eCAS. Can someone withdraw money?"* | Exposure register — states what the artefact structurally enables, **without ever saying you're safe** |
| *"I scanned a QR code and gave them the OTP. Can they take my money?"* | **Escalated** before any other branch. No analysis, no reassurance — straight to the bank |

[**Recorded runs with full decision traces →**](https://<user>.github.io/consent-lens/)

## How it works

```
question
  │
  ├─[CODE]  escalate.check()   FIRST, unconditionally. Someone who has already given
  │                            away a credential needs their bank, not an explanation.
  │
  ├─[CODE]  guard.classify()   pre-generation. Advice and adjudication questions
  │                            never reach the generator as questions to answer.
  │
  ├─[AGENT] tool-calling loop  identify_route · retrieve_clauses ·
  │                            check_gap_register · check_exposure_register
  │                            → answer | abstain
  │
  ├─[CODE]  guard.audit()      every factual sentence must map to a citation.
  ├─[CODE]  guard.assurance()  no answer may tell anyone they are safe.
  │
  └─ trace → logs/traces/*.json
```

**Precedence is strict: escalation > refusal > answer.** Safety outranks the boundary; the
boundary outranks helpfulness. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full decision
path and an honest account of what is and isn't agentic here.

**The guard is deterministic; the reasoning is agentic.** An agent that can be talked out of
refusing is not a guard. Both ends are plain functions you can read in a minute — that is
deliberate, and it is why there is no vector database and no RAG framework here. The corpus
is a few hundred clauses; a normalised matrix and a dot product is the correct tool at that
size, and every layer has to be explainable without hand-waving.

Chunking follows **clause boundaries**, not token windows. The promise is "the spec says X,
here, in clause Y" — and a citation pointing at half a clause is not a citation.

Retrieval runs on **local embeddings** (no API key). Only generation calls out.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY

python -m consent_lens.fetch  # snapshot the corpus with retrieval dates
python -m consent_lens.chunk  # clause-boundary chunking
python -m consent_lens.index  # embed

python -m consent_lens.cli --trace "I forwarded my eCAS for free advice. What can they do with it?"

python demo/run_demo.py && python demo/make_page.py   # rebuild docs/index.html
```

## The failure log

[`logs/failures.md`](logs/failures.md) — kept from the first query, **not tidied**.

Each entry is classified: `retrieval` · `generation` · `corpus` · `framework`. That last
distinction is the point. "My system failed" and "the framework does not cover this case"
are different findings, and only one of them is mine to fix.

Entries **0a** and **0b** were logged before any code ran: the project's own requirements
document asserted a framework exclusion that was never established, and cited a clause
number that does not exist. Written by a careful human, slowly, in a document about the
difference between what a source says and what sounds right. That is why the citation audit
runs in code after generation rather than being asked for in a prompt.

## What this is not

**It never tells anyone they are safe.** It states what an artefact structurally enables — an
eCAS carries no credentials, so it does not by itself permit a redemption — and stops there.
"You're fine" is an assurance, and this product cannot make one: it does not know what else was
shared. A separate deterministic check discards any answer containing assurance language.

Not an AA integration. Not a product. No real financial data touches it, in any environment.
No consent-flow redesign, no DPDP overlap, no second corpus, no UI worth the name. Those are
[documented decisions](consent-lens-prd.md), not omissions.

It is the smallest honest probe of one question: **is comprehension the bottleneck?**

## Status

Three-day build. Corpus, retrieval, guard, agent loop, gap register and failure log are real.
Everything marked ⚠ in the PRD is asserted from secondary sources and not yet verified
against the primary documents — including the joint-account question above.

## Licence

MIT. The corpus documents belong to their publishers and are snapshotted here with retrieval
dates for citation verifiability.
