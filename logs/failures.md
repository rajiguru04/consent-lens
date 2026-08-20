# Failure log

Kept from the first query onward. **Not tidied.** The failures are the finding.

Each entry classifies the cause, because the difference between *my system failed* and
*the framework does not cover this* is the whole point of the exercise.

**Classes**
- `retrieval` — the right clause exists in the corpus and was not returned
- `generation` — the right clause was returned and the answer misused it
- `corpus` — the answer exists in a document that is not in the corpus
- `framework` — no document answers it, because the framework does not cover the case

---

### 0a — asserted a framework exclusion that was never established
**Asked:** *(none — this was in the PRD, before any code ran)*
**Claimed:** joint accounts are excluded from the Account Aggregator *framework*.
**Wrong because:** the evidence shows only that no bank supports joint-account discovery
in practice. Whether that is a specification exclusion or universal non-implementation was
never established. Asserted as settled fact, sourced to nothing.
**Class:** `framework` — and precisely the confusion this build exists to detect.

### 0b — invented a clause number
**Asked:** *(none — PRD draft)*
**Claimed:** "RBI Master Direction NBFC-AA, cl. 6.3" as the authority for an FIU data-retention rule.
**Wrong because:** the citation was fabricated before the corpus had been fetched, and the
NBFC-AA Master Direction regulates Account Aggregators rather than FIU retention of received
data — so the rule may not live there at all.
**Class:** `corpus` (rule likely governed elsewhere) compounded by an invented citation.

> Both were written by a careful human, drafting slowly, in a document *about* the difference
> between what a source says and what sounds right. An LLM retrieving quickly will make the
> same error faster. That is why the citation audit runs in code after generation rather than
> being requested in a prompt.

---

### 1 — HTML dispatch silently discarded every real clause number
**Asked:** *(none — build-time, first chunking run over the fetched corpus)*
**Answered:** 186 chunks, RBI Master Direction split into `para 1 (no clause numbering
found)` ... `para 168 (no clause numbering found)` — sequential paragraph anchors, no clause
numbers, for all 168 RBI chunks.
**Wrong because:** `build()` routed every HTML source through `chunk_markdown()`, which
splits on `#`-style markdown headings. Stripped HTML never has those, so it always returned
an empty list, and `or _chunk_paragraph_anchored(...)` silently took over — even though
`chunk_numbered()`, written for exactly this case, was sitting unused in the same file and
the RBI text plainly contains real numbering (`"6.3 The consent of the customer obtained by
the Account Aggregator..."`). Confirmed by running `chunk_numbered` directly against the same
file: 62 correctly-numbered clauses, including `cl. 6.3` and `cl. 7.1`, the two the demo
leans on. This would have shipped resolvable-looking but fabricated citations (`"para 72"`)
for the one source with binding authority — worse than no citation, per the brief's own
standard.
**Class:** `retrieval` — the closest fit, though it sits upstream of retrieval proper: the
correct clause was present in the corpus and even present in the code (`chunk_numbered`), just
never wired to the HTML path. The four-class taxonomy has no bucket for "right function
existed, wrong function got called" — worth a line in the note if this recurs.
**Fixed?** yes — `build()` now calls `chunk_numbered()` directly for `kind == "html"`, which
already falls back to paragraph anchors internally when no numbering is found (confirmed
harmless on DEPA, which has no numbered clauses). Re-run: 80 chunks total (62 RBI + 10 DEPA +
8 Sahamati), all RBI chunks now carry real clause IDs.

---

### 2 — ADJUDICATION guard missed named-entity phrasing
**Asked:** *(none — build-time, exercising `guard.classify()` against the demo set plus
adversarial variants before any generation was wired in)*
**Answered:** `"Is Account Aggregator safe?"`, `"Is Perfios trustworthy?"`, `"Is NSDL AA a
scam?"`, `"Is CAMSFinserv safe to share my data with?"` all classified `ANSWERABLE` — the
refusal boundary the product exists to demonstrate did not fire.
**Wrong because:** the ADJUDICATION pattern required `is/are/was/were` to be immediately
followed by a demonstrative (`this|that|the|these|those|they`) before the safety adjective —
so it caught `"is **that** service trustworthy"` but not `"is **Perfios** trustworthy"`. Real
questions about a named AA-ecosystem entity (an actual FIU/FIP/AA participant — Perfios, NSDL
AA, CAMSFinserv, Sahamati) don't carry an article before the name. 6 of 8 realistic phrasings
tested slipped through. This is the same shape as entry 1: the guard *looked* like it covered
the case, and only testing against realistic phrasing (not just the README's demo sentence,
which happens to use "that") surfaced the gap.
**Class:** `retrieval` — again an imperfect fit; this is a classification/guard defect, not a
retrieval one, and the taxonomy still has no bucket for it. Two entries in now with the same
mislabel — if a third shows up, add a `guard` class rather than keep forcing these into
`retrieval`.
**Fixed?** yes — made the demonstrative optional in the pattern
(`consent_lens/guard.py`). Re-tested: all 8 named-entity variants now correctly classify
`ADJUDICATION`; the original demo/adversarial set is unchanged; a separate batch of 8
clearly-answerable factual questions (including "is"-phrased ones like *"Is the consent
artefact digitally signed?"*) all still pass as `ANSWERABLE` — no observed false-positive
cost from widening the match.

---

### 3 — the citation audit didn't check citations were real
**Asked:** *(none — build-time, reviewing `agent.py`/`guard.py` before any live generation
was run)*
**Answered:** `guard.audit()` returned `(True, [])` for the answer text *"...per clause
12.4."* with citation `"RBI Master Direction, cl. 12.4 (retrieved 2026-08-20)"` — a clause
number that does not exist anywhere in the corpus (confirmed: zero chunks match `12.4`).
**Wrong because:** `audit()` only checks that the citations list is non-empty when the answer
has factual sentences — it never checks that a citation string is one `retrieve_clauses`
actually returned. In `agent.py`, the `answer` tool call's `citations` array is written by
the model itself and was passed straight to `audit()` with no membership check
(`cites or citations` silently fell back to the retrieved pool only when the model supplied
nothing at all). A model that gets nervous about a gap and invents a plausible-sounding
clause number — exactly what happened by hand in entry 0b — would sail through the exact
mechanism the README describes as preventing it ("the citation audit runs in code after
generation rather than being asked for in a prompt"). This is the most consequential bug
found so far because it defeats the product's central claim on the path that matters most:
model-generated answers, not build-time review.
**Class:** `generation` — this one fits the taxonomy cleanly, unlike entries 1 and 2.
**Fixed?** yes. `agent.py` now tracks `retrieved_clause_ids` (populated by `retrieve_clauses`
alongside the existing `citations` accumulator) and rejects any model-supplied citation that
doesn't reference a clause_id from that pool, before `audit()` even runs. First attempt at the
fix used plain substring matching and had two more bugs, caught immediately by testing against
realistic phrasing rather than trusting the diff: (a) it rejected true citations phrased
differently from `Chunk.citation()`'s exact format — e.g. "clause 6.4" doesn't contain the
literal substring "cl. 6.4" — which would have made the guard reject correct answers; (b) a
fabricated "cl. 16.4" would have **false-passed** against a real "cl. 6.4", because "6.4" is
literally a substring of "16.4". Fixed by matching the clause number's numeric core with a
regex word boundary (`_cites_clause()` in `agent.py`) instead of raw substring containment.
Verified against four cases: real clause paraphrased (accept), real clause exact-format
(accept), fabricated clause never retrieved (reject), and the 16.4-vs-6.4 collision (reject).

---

### 4 — flagship demo question tried to cite tool outputs, not clauses
**Asked:** *"I forwarded my eCAS to a portfolio advisory service for free advice. What can
they do with it?"* — first live end-to-end run, via `cli.py --trace`.
**Answered:** `AUDIT_FAILED`. The model called `identify_route` (route=ECAS, ungoverned) and
`check_exposure_register` (no credentials, no redemption capability) — both correct — but
never called `retrieve_clauses`, then tried to answer with citations
`"check_exposure_register output: eCAS carries no credentials..."` and `"identify_route
output: eCAS forwarding is not governed..."`.
**Wrong because:** register tool outputs are not citable sources — the exposure register's
own `evidence` field literally says `"Author's assessment from domain knowledge"`, not a
document citation. The system prompt never states what counts as a valid citation (only
`retrieve_clauses` results do), and never tells the model it still needs to call
`retrieve_clauses` to state "what AA would have given" — the comparison half of exactly what
this demo question is supposed to prove (BUILD-PLAN.md, Q1). This is the first live
validation that entry 3's fix works as intended — it correctly blocked an ungrounded citation
— but it also shows the flagship demo question doesn't fully succeed yet.
**Class:** `generation`
**Fixed?** partially. The system prompt now states only `retrieve_clauses` output is citable
and that comparison claims ("what AA would have given") need their own `retrieve_clauses`
call. Live re-run: the model now correctly calls `retrieve_clauses` (`cl. 9.1`, `cl. 7.6`) and
no longer tries to cite tool outputs — the specific bug here is gone. It still ends up
abstaining rather than producing the rich comparison answer the demo wants, but that's now a
content/quality question, not a citation-fabrication one, and it's caught safely by entry 5's
guard rather than leaking an ungrounded claim.

**Addendum, after adding a real eCAS/CAS source.** The root cause above was partly a corpus
gap, not just a prompting one: nothing in the corpus actually explained what a CAS/eCAS *is*.
User found the CDSL CAS FAQ (cdslindia.com/cas/FAQ.html) — the only source found covering
eCAS specifically, citing real SEBI circular CIR/MRD/DP/31/2014 — and it's now wired in as 13
Q&A chunks (`cdsl-cas-faq`, `authority: public-awareness`, new `chunk_faq()` parser for its
Bootstrap accordion structure, since neither the numbered-clause parser nor the whole-page
poster parser fit a 13-entry FAQ). Retrieval confirmed strong: querying "what is eCAS" scores
0.690 against the CDSL content. Live re-run of this exact question, though, still abstains —
the model reasoned via `identify_route` + `check_exposure_register` and never called
`retrieve_clauses` at all, so the new content was available but unused. This isolates the
remaining gap precisely: it's no longer a corpus gap, it's purely the same orchestration
reliability issue as entries 4/6 (the model doesn't consistently reach for the tool even when
told to) — worth returning to if Q1 needs to fully succeed, but out of scope for "add this
source," which is now done and verified.

**Second addendum, `demo/run_demo.py` full-suite run.** A closely related question — *"I
shared my mutual fund holding statement by eCAS. Can someone withdraw money from that
account?"* — hit `AUDIT_FAILED` for the same reason: the model cited
`check_exposure_register`'s free-text `evidence` field ("Author's assessment from domain
knowledge...") instead of a real `retrieve_clauses` result, even though it had correctly
retrieved three real CDSL FAQ clauses earlier in the same turn. Confirms this is a live,
recurring behavior, not a one-off — still open, still the same fix needed (tighten what the
model is allowed to treat as a citable source). Publishing this outcome as-is on the demo
page rather than re-rolling for a cleaner result: `AUDIT_FAILED` is the guard correctly
blocking an ungrounded claim, which is the mechanism the whole product exists to demonstrate.

**Third addendum, after entry 11's precedent fix.** Re-ran the full suite: this same question
(and Q1) still hit `AUDIT_FAILED`, confirming entry 11 doesn't touch this path — and correctly
so. Entry 11 only helps when the model supplies NO citations and its claim is precedent-
covered; here the model actively puts `evidence` text into the `answer` tool's `citations`
array as if it were real, which the membership check (entry 3/10) still correctly rejects as
fabricated. Two of seven demo questions now genuinely improved this session (Q2, Q3: `ABSTAINED`
→ `ANSWERED`); this specific behavior remains open, and the fix is different from entry 11's —
the model needs to stop reaching for `citations` at all when it only has register reasoning,
not corpus clauses, to offer.

---

### 5 — `abstain()` bypasses both guards entirely
**Asked:** *"My relationship manager said 'you'll get an OTP, approve the next screen.' What
did I approve?"*
**Answered:** `ABSTAINED`, reason `NOT_IN_CORPUS` — but the abstain `text` itself asserts an
uncited factual claim: *"...the consent artefact must show who will receive data, what data,
and for what purpose..."* — a paraphrase of `cl. 6.3`, delivered with zero citation and zero
guard check.
**Wrong because:** `agent.py`'s `abstain` branch returned `call.input["text"]` straight to the
user with no call to `audit()` or `assurance_check()` — unlike the `answer` branch, which runs
both. The `abstain` tool's `text` field is entirely free-form model output, so nothing stopped
it from asserting uncited facts, and in principle nothing would stop it asserting assurance
language ("you're safe") either — the exact thing `assurance_check()` exists to block. Same
defect class as entry 3 (a boundary claimed as "enforced in code" that wasn't, in practice),
but this time on the one path with zero enforcement, not partial enforcement.
**Class:** `generation`
**Fixed?** yes. The `abstain` branch in `agent.py` now runs `audit(text, [])` and
`assurance_check(text)` before returning — citations is always `[]` for abstain by design, so
this acts as a hard rule: abstain text may explain the boundary, never assert facts. Either
check failing replaces the text with a safe generic fallback (`"I can't answer that from these
documents. ({reason_code})"`), reason_code preserved. Verified deterministically against the
exact captured text above (live re-runs are non-deterministic and didn't reliably reproduce
the same trajectory): `audit()` now correctly fails all three sentences as unsupported,
confirming the fix catches this case. Not yet re-verified live against a model that reaches
`abstain` with a similarly uncited claim — worth doing before calling this closed.

---

### 6 — model skipped tool calls entirely; discarded reasoning isn't logged
**Asked:** *"Can I take it back? Do they delete what they already have?"* and *"What about the
account I hold jointly?"*
**Answered:** Both returned the generic `no_tool_call` fallback — *"I can't answer that from
these documents."* The model responded in plain prose with no tool call at all, and
`agent.py`'s `no_tool_call` branch discards that prose without recording it in the trace.
**Wrong because:** both questions have a plausible registry match that was never reached —
`check_gap_register`'s "joint accounts" entry (`r"\bjoint (account|holding)"`) would very
likely fire on a topic like "joint account," and `retrieve_clauses` likely has
revocation-adjacent clauses for the deletion question (`cl. 6.6` surfaced for "can I revoke my
consent" during the earlier retrieval smoke-test). Without the discarded prose captured in
the trace, there's no way to tell whether the model reasoned toward the right register and
declined to call it, or missed the connection entirely — the failure is opaque by
construction.
**Class:** `retrieval` — third entry forced into a class that doesn't quite fit (see entries 1
and 2's note). Three for three now on the guard/orchestration-shaped gap in the taxonomy —
this confirms it's a real hole, not a one-off.
**Fixed?** partially, and inconsistently. Added "EVERY turn must call exactly one tool; a
plain-text reply is discarded and treated as a failure" to the system prompt. Live re-run:
fixed for the joint-account question — the model now calls `retrieve_clauses` and
`check_gap_register` instead of returning prose. **Not fixed** for the revocation/deletion
question — identical `no_tool_call` fallback, same failure, same wording, even after the
prompt change. The discarded-prose observability gap (part b of the original fix plan) was
not addressed — still no way to see what the model wrote instead of calling a tool. Worth
noting for the product note: a system-prompt instruction is not a guarantee, and this is the
concrete evidence — same instruction, one question fixed, one unchanged.

---

### 7 — the abstain guard (entry 5) and the gap register fought each other
**Asked:** *"What about the account I hold jointly?"* — live re-run after entry 6's partial
prompt fix, which got the model calling `check_gap_register` for the first time on this
question.
**Answered:** `check_gap_register` correctly found the joint-accounts `UNRESOLVED` entry and
handed the model its pre-written, human-vetted `Gap.user_text` as `suggested_wording`. The
model paraphrased it in its own words for the `abstain` call instead of using it verbatim.
Entry 5's new guard — correctly, by its own rule — flagged that paraphrase as an uncited
factual claim and replaced it with the bland generic fallback, discarding a *correct* answer.
**Wrong because:** the register did its job and the guard did its job, but the two mechanisms
weren't designed to work together — `audit()`/`abstain`'s bar (any factual sentence needs a
citation, and abstain never carries one) can't distinguish "the model invented this" from "the
model is restating something a human already vetted for exactly this situation." Right after
fixing one real gap (entry 5), it created a false positive against a legitimate, designed-for
case.
**Class:** `generation`
**Fixed?** yes. Added `guard.audit_abstain()`: a factual sentence in abstain text is now
allowed through if it substantially restates a known precedent (a `Gap.user_text` this
conversation actually retrieved), measured by word-overlap coverage of the *sentence* by the
precedent — not exact match, so paraphrasing doesn't falsely fail, and not the reverse
direction, so a short sentence riding in on a long precedent can't claim more than it actually
restates. `agent.py` now tracks `gap_texts` (populated by `check_gap_register`) alongside the
existing `citations`/`retrieved_clause_ids` accumulators. Verified against three cases: the
real gap paraphrase now passes; the original entry-5 uncited claim still fails; and — the
adversarial case that actually matters — a fabricated, unrelated claim still fails even when
`gap_texts` is non-empty, confirming this isn't a blanket bypass once any gap has been found.

---

### 8 — the gap register misses its own topic, paraphrased
**Asked:** *"What about the account I hold jointly?"* — same live re-run as entry 7, one call
later.
**Answered:** `check_gap_register` returned `{"found": false}` for the topic string *"jointly
held account consent authorization required from all holders"* — despite the joint-accounts
entry existing in the register and having fired moments earlier in a different run of the
same question.
**Wrong because:** `registry.py`'s pattern (`r"\bjoint (account|holding)"`) requires the
literal adjective-noun pair "joint account" or "joint holding." The model's own topic
paraphrase this run — "jointly held account" — uses the adverb "jointly," which the regex does
not match. `check_gap_register`'s `topic` argument is free-form model output, not a fixed
vocabulary, so whether the right entry fires now depends on how the model happens to phrase
its own tool call — the exact same question can hit or miss the register run to run. With no
match, `gap_texts` was empty, so entry 7's fix correctly rejected the model's now-genuinely-
uncited claim — the guard behaved correctly given what it was told, but the underlying
register lookup is the unreliable part.
**Class:** `retrieval` — closest fit again, though as with entries 1/2/6 it's really a
guard/orchestration-layer defect, not a corpus retrieval one.
**Fixed?** yes. `_run_tool`'s `check_gap_register` branch now also tries matching against the
original user question, not only the model's topic paraphrase — `check_gap_register(topic) or
check_gap_register(question)`. Same fix applied to `check_exposure_register` on the same
reasoning (identical brittleness risk, identical pattern-matching design in `registry.py`),
even though it wasn't the one observed failing here — the two tools share the exact same
defect shape, so patching one and leaving the other is just deferring the same bug to whenever
it happens to surface there instead. The topic-or-question fallback alone turned out to be
insufficient for the actual observed case — the raw question ("What about the account I hold
jointly?") didn't match the register pattern either, since it also required "joint" adjacent
to "account"/"holding" and never covered "hold ... jointly" or "jointly held" phrasing. Fixed
the pattern itself in `registry.py` to cover both word orders and the adverb form. Verified
against 6 real phrasings (all match) and 3 unrelated questions including an adversarial
near-miss, "joint venture between banks and AAs" (none false-positive). Live end-to-end
re-run confirms the full chain now works: `check_gap_register` finds the entry,
`audit_abstain` (entry 7) correctly recognizes the model's paraphrase as covered by the
precedent, and the final answer is a clean, correctly-hedged UNRESOLVED response — this is
Q5's intended outcome from BUILD-PLAN.md, working for the first time.

---

### 9 — three pipeline bugs found while wiring in a real manual corpus (public-awareness)
**Asked:** *(none — build-time. User saved 8 real pages from rbikehtahai.rbi.org.in
(CAPTCHA-gated, so manual-only) into `corpus/manual/`; this is the first real content ever
pushed through the manual-source path, which until now only had placeholder plumbing.)*
**Answered:** Three separate silent failures, each one masking the next until fixed in turn.
**Wrong because, and fixed:**
- **(a) fixed-id list never matched reality.** `fetch.py`'s original `MANUAL_SOURCES` was 7
  ids/URLs *guessed* before anyone had seen the real site (entries like `rbi-aware-qr`,
  `rbi-aware-cautions`). None of the 8 real saved filenames matched, so none would have been
  picked up at all. Rewrote to auto-discover `corpus/manual/*.html` instead of requiring
  pre-guessed filenames — the id/title now comes from the file the user actually saved.
- **(b) the chrome-stripping boundary silently no-opped on one file.** The site repeats an
  identical language switcher and a sitewide nav menu (every topic on the site) on every page.
  First cleaning attempt cut the nav menu at the trailing marker `"Back to Home"` — but one
  saved page's DOM didn't contain that string at all, so the split did nothing and the entire
  ~1.6KB nav menu passed through disguised as real content, while the file's actual message
  (Tokenisation) was genuinely never captured in the static save. Fixed by cutting at the nav
  menu's own first item (`"Account Aggregator Facility"`), present and stable in every file,
  rather than a trailing marker that isn't. Also added a length-based skip (<200 chars of
  cleaned content) and a content-hash dedup (one file was a near-duplicate landing page).
- **(c) the paragraph-length threshold silently dropped two entire documents.**
  `_chunk_paragraph_anchored`'s `>80 chars` per-paragraph bar was calibrated for the RBI
  Master Direction's long legal prose. These are short poster-style messages — each *line*
  ("Beware of tempting pop-ups!") is well under 80 chars even though the combined message is
  substantive — so every paragraph in 2 of 6 sources got filtered out, silently producing zero
  chunks for those documents. Same failure shape as entry 1: the pipeline reporting success
  while quietly discarding real content. Added `_chunk_whole_page()` — one chunk for the
  entire cleaned page — used instead of paragraph-splitting whenever `authority ==
  "public-awareness"`, since these pages are one coherent short message, not a document with
  independently meaningful paragraphs.
**Class:** `corpus`/`retrieval`, split across three sub-bugs — none of them a corpus-content
problem (the real content existed all along); all three are pipeline defects that would have
either silently dropped it or silently mislabeled it.
**Fixed?** yes, all three. Verified end to end: 6 of 8 saved pages produced real, correctly-
titled, single-chunk sources (`rbi-kehta-hai-digital-arrest`, `-aa`, `-rules-when-using-aeps`,
`-digital-banking-safeguards`, `-limit-loss-on-fraud`, `-unknown-popups`); Tokenisation
correctly skipped with a re-save prompt (content genuinely wasn't captured); the near-duplicate
correctly resolved to the better-titled file, not whichever sorted first. Live retrieval
confirms the new content is actually reachable: *"someone called saying I am under digital
arrest"* retrieves `rbi-kehta-hai-digital-arrest, full page` at 0.713 similarity — the highest
score of any query run this session.

---

### 10 — the citation-membership fix (entry 3) had its own boundary bug
**Asked:** *"I shared my mutual fund holding statement by eCAS. Can someone withdraw money
from that account?"* — one of the 7 questions in `demo/run_demo.py`, first live run after
adding the CDSL CAS FAQ source and pushing to GitHub.
**Answered:** `AUDIT_FAILED`, despite the model correctly calling `retrieve_clauses` three
times and citing real, retrieved CDSL FAQ chunks verbatim. `_cites_clause()` — entry 3's own
membership check — rejected every one of them as `unverified_citations`.
**Wrong because:** `_cites_clause()` used `\bcore\b` to bound the match, which works for
numeric clause codes ("6.4") but breaks for `chunk_faq()`'s clause_ids, which are the
question text itself and often end in punctuation ("...(CAS)?"). `\b` requires a transition
between a word and non-word character; "?" and the space following it in a real citation are
both non-word, so no boundary ever fires there — `\b...\b` failed to match even a
byte-for-byte, character-for-character substring. Confirmed directly: `clause_id in citation`
→ `True`; `_cites_clause(citation, clause_id)` → `False`. Entry 3's fix had never been tested
against a non-numeric clause_id, because no such source existed until this session's CDSL
integration created one.
**Class:** `generation` — a real citation was rejected as fabricated, the inverse failure
direction from entry 3 itself (which was invented citations passing). Both are the same
underlying lesson: a guard that only gets tested against the shapes of input that existed
when it was written will have gaps at the shapes that didn't.
**Fixed?** yes. Replaced `\b...\b` with `(?<!\w)...(?!\w)` — lookarounds that only care
whether the match is flanked by a *word* character (the actual collision risk this boundary
exists to catch, per entry 3's 16.4-vs-6.4 case), not whether it's flanked by any non-word
character at all. Verified against all 5 cases together, including the original entry-3
regression set: real clause paraphrased (accept), real clause exact-format (accept), the
16.4-vs-6.4 collision (still correctly rejected), and this entry's FAQ punctuation case
(accept) — all 5 match expected outcomes, no regressions.

---

### 11 — the exposure register had no path to a passing answer, at all
**Asked:** *"I uploaded my ICICI bank statement for home loan processing with another bank.
Will my bank account be subject to fraud?"* — user-reported, after using the deployed app
directly, framed as "is my RAG not comprehensive enough?"
**Answered:** `ABSTAINED (ROUTE_NOT_GOVERNED)`, with the actual reasoning (route correctly
identified as `PDF_UPLOAD`/ungoverned, exposure register correctly found: no debit capability,
but salary/EMI/account-number profiling risk) discarded and replaced by the generic fallback.
**Wrong because:** this was misdiagnosed at first as a retrieval-coverage problem — it isn't.
`identify_route` and `check_exposure_register` both worked correctly. The real cause: **all
three** exposure register entries (`eCAS`, `bank statement PDF`, even `Account Aggregator
consent`) are `verified=False`, sourced to `"Author's assessment from domain knowledge"` —
never corpus-cited. So any answer drawing on the register had no real citation to attach, and
the citation guards correctly refused to let it through uncited — on `answer()` (entry
3/10's membership check) as much as `abstain()` (entry 5/7's guard, no gap-register precedent
covers exposure content). **Every exposure-driven question was structurally blocked before
this fix, regardless of what the corpus contains** — not a narrow miss, the entire mechanism
the demo calls "the exposure register" (README) had no working exit.
**Class:** `generation` — though it sits closer to an architecture gap than a single bug: a
whole category of legitimate, correctly-reasoned answers had no passing path.
**Fixed?** yes, deliberately choosing "common sense within the guardrails" over "make every
claim corpus-cited" (user's explicit call, given both options). `guard.audit()` and
`guard.audit_abstain()` (entry 7) merged into one `guard.audit_claims()`: a factual sentence
passes with a real citation (existing rule, unchanged) OR by substantially restating a known
precedent — now `identify_route`'s structural note and the exposure register's
`does_not_enable`/`does_enable` text, in addition to entry 7's `Gap.user_text` — word-overlap
matched, not exact. Passing on precedent alone appends a visible disclaimer
(`COMMON_SENSE_DISCLAIMER`) so the boundary between "cited fact" and "structural reasoning,
not sourced from a document" stays honest rather than blurred. Calibration was not a guess:
the gap-register threshold (0.6) still failed the real captured case (0.25 / 0.52
sentence-coverage) because a model restating structural reasoning in flowing prose shares far
less literal vocabulary than it does when closely paraphrasing pre-written text.

First calibration pass (0.5) still failed the actual motivating case once entry 12's route
fix let `identify_route` classify correctly: the model's real abstain text combined the route
note AND the exposure register into one synthesized sentence ("uploaded, so ungoverned, and
it doesn't carry credentials either"), scoring only 0.20 / 0.31 against either precedent
*separately* — because `covered_by_precedent` was checking per-precedent max, not their
union, and a sentence legitimately drawing on two tools called the same turn will never score
well against either alone. Fixed by checking the union of all retrieved precedents' vocabulary
instead (still bounded — only what tools actually returned this conversation, never the whole
corpus); that raised the same sentence to 0.43. Threshold then re-picked empirically at 0.4 —
the highest value that passes both real cases (this one and entry 7's gap paraphrase) while
still rejecting every adversarial case tested (entry 5's unrelated uncited claim, the
fabricated-clause case, and a sentence built specifically to probe this exact change — real
vocabulary overlap with a precedent, but asserting something false, "...is completely safe
from any kind of misuse" — still correctly rejected, both on coverage and by
`assurance_check()` as a backstop). Margin checked, not assumed: 0.35 and 0.3 also pass the
full battery, so 0.4 isn't sitting at the edge of what it needs to reject.

**Live end-to-end confirmation**, the user's exact original question, after all three fixes
(entry 11's precedent mechanism, entry 12's route-pattern fix, and the union-coverage
correction above): *"I uploaded my ICICI bank statement for home loan processing with another
bank. Will my bank account be subject to fraud?"* now returns a real, honest, correctly-hedged
answer — *"You uploaded a PDF statement directly, which is not governed by the Account
Aggregator consent framework. The corpus does not cover what happens to documents uploaded
this way or what security practices the receiving organisation uses."* — with the disclaimer
attached, `audit_passed: true`, `assurance_passed: true`. Previously: the generic fallback,
three separate times, for three different reasons.

---

### 12 — route classification broke on a named bank inserted mid-phrase
**Asked:** same question as entry 11, re-run after the entry-11 fix.
**Answered:** `identify_route` returned `UNKNOWN` for *"uploaded my ICICI bank statement..."*
— on the SAME question that had correctly classified as `PDF_UPLOAD` moments earlier, without
the bank name.
**Wrong because:** `ROUTE_PATTERNS`' `PDF_UPLOAD` regex required `"upload(ed)? (my |the
)?(bank )?statement"` — a rigid adjacency between "my/the" and "statement" that "ICICI"
breaks by sitting in between. Real users name their bank. Same defect shape as entries 2 and
8 (a rigid regex tuned against the README's own example phrasing, not against realistic
named-entity variation) — and this is the THIRD time this exact shape has surfaced, now
clearly a pattern in how these registers get written, not a one-off. With route stuck at
`UNKNOWN`, entry 11's fix had no route-note precedent to draw on either, so the model's
otherwise-correct reasoning failed the guard a second time for a compounding reason.
**Class:** `retrieval` — the now-familiar imperfect fit (fourth entry in this bucket:
1/2/8/12 — a `guard`/pattern-matching class is overdue if this taxonomy gets revisited).
**Fixed?** yes. Added a bounded word-gap, `(?:\w+\s+){0,5}`, between the anchor word and
"statement" in both `PDF_UPLOAD` and `ECAS` (same defect shape existed in both). Verified
against 6 real phrasings including the original ICICI case and a longer one ("forwarded my
mutual fund holding CAS statement by email" — needed the wider `{0,5}` bound; `{0,3}` still
missed it) — all 6 correctly classified. Re-verified 3 adversarial/unrelated sentences
(including one deliberately padded with extra words around unrelated uses of "statement")
still correctly return `UNKNOWN` — the widened bound didn't loosen false-positive risk.

---

### 13 — HEDGES only recognized negative-phrased boundary statements
**Asked:** same question as entries 11/12, user re-ran it independently after those fixes
shipped and reported it still failed.
**Answered:** `ABSTAINED` with the generic fallback again. Trace showed real progress this
run — route correct, exposure register found, one sentence passed via entry 11's precedent
mechanism — but a second sentence, *"The corpus only covers data shared via the Account
Aggregator framework,"* failed as `unsupported`, taking the whole answer down with it.
**Wrong because:** that sentence isn't a claim needing a citation or precedent at all — it's a
meta-statement about the corpus's own scope, exactly the category `HEDGES` exists to exempt.
But `HEDGES` only matched the negative phrasing (`"the corpus does not..."`), not this
positive one (`"the corpus only covers..."`) — a phrasing difference, not a different kind of
statement. This is model non-determinism surfacing a real, narrower gap: the same question
generates a different sentence split run to run, and this run happened to hit a hedge shape
the regex didn't cover. Entries 11/12 were both real, verified fixes — this is a third,
distinct gap in the same feature, not a regression of either.
**Class:** `generation`
**Fixed?** yes. Extended `HEDGES` to also match `"the (documents/specification/corpus) only
(covers/addresses/applies to/governs/includes)..."`. First attempt had its own bug, caught
before shipping: `addresses?` only makes the final "s" optional, so it matched "addresses"
but not the bare verb form "address" — fixed to `address(es)?`. Verified against 5 phrasing
variants (covers/address/applies to/governs/includes) — all now correctly exempted. Live
re-run of the user's exact question confirmed end to end: `audit_passed: true`, real answer
delivered with the common-sense disclaimer, not the generic fallback.

**Correction, further live testing.** That "confirmed end to end" was one successful run, not
a settled result — the user re-ran the same question independently and hit `ABSTAINED` again,
for a fourth distinct reason (entry 14). Leaving this claim as originally written rather than
editing it after the fact: it was true of that run, and the gap it closed was real, but it
wasn't the last gap. See entry 15 for what that pattern turned out to mean.

---

### 14 — a factual clause and a hedge clause joined by "but" were graded as one unit
**Asked:** same question again, next live run.
**Answered:** `ABSTAINED`, generic fallback. The failing sentence: *"The statement does not
carry login credentials, so it cannot by itself enable a withdrawal or debit—but the corpus
does not address what other fraud risks may apply to documents shared outside the AA
framework."*
**Wrong because:** this is genuinely two different kinds of statement stapled together by
ordinary English — a precedent-backed factual claim, then (after "but") a scope/boundary
hedge. `HEDGES.match()` only checks a clause's *start* (`^`), so it never even looked at the
hedge half once "but" buried it mid-sentence — and evaluating the whole compound sentence as
one unit for precedent-coverage meant the hedge clause's unrelated vocabulary (fraud risks,
documents shared outside the framework) diluted the ratio below threshold, rejecting a
sentence where each half was actually fine on its own.
**Class:** `generation`
**Fixed?** yes. Split candidate clauses on `but`/`however`/`yet` (`CLAUSE_SPLIT`) in addition
to sentence-ending punctuation, so each half is graded independently. Verified against 7
cases together: this sentence and entry 11's original compound sentence (both MUST PASS), the
existing gap-paraphrase and three unrelated/fabricated adversarial cases (MUST FAIL,
unchanged), and a new adversarial case built specifically to probe this exact change — a
fabricated claim riding along with a legitimate hedge clause via "but" — still correctly
rejected, since clause-splitting evaluates each half on its own merits rather than letting a
real hedge vouch for an unrelated fabrication next to it.

---

### 15 — decided to stop patching HEDGES phrasing gaps and document the limitation
**Asked:** same question, next live run, after entry 14 shipped.
**Answered:** `ABSTAINED` again — a *third* distinct hedge-phrasing gap: *"...so the RBI
Master Direction and Sahamati specifications do not define what restrictions apply..."* The
model named the actual document titles instead of the generic words (`"documents"`,
`"corpus"`, `"specification"`) `HEDGES` is written to recognize.
**Wrong because:** this isn't one bug, it's the same root problem surfacing a third time in a
row on the same question (entries 13, 14, 15). `HEDGES` tries to recognize "this is a
scope/boundary statement" by enumerating phrasings via regex — but a model can express that
one idea in effectively unlimited ways: generic or specific document names, positive or
negative framing, sentence-initial or buried mid-clause. Each individual fix (11, 12, 13, 14)
was real and independently verified — this isn't a case of a sloppy patch — but the
underlying approach (classify free text after the model writes it) structurally cannot keep
pace with natural-language variety. Continuing to patch phrasing-by-phrasing narrows the gap
without ever closing it.
**Class:** `generation` — and, honestly, an architecture-level finding as much as a bug: the
real fix isn't another regex, it's changing what the model is asked to produce. `answer()`/
`abstain()` currently take one free-text paragraph that this code parses and classifies after
the fact; a more robust design would have the model submit typed claims directly —
`{text, support: "citation" | "precedent" | "scope_note"}` — so it explicitly declares what
kind of statement each sentence is, rather than this code inferring it from phrasing.
**Fixed?** no — deliberately. Presented this choice directly rather than shipping a fourth
regex patch: redesign the tool schema now, patch once more, or stop and document. Decided:
stop and document as a known, understood limitation — not a mystery, not a sloppy fix,
correctly triaged as "the framework this system operates on has a real edge" rather than "my
system failed." Belongs in the product note's "what I deliberately did not build to full
rigor" section (brief §7): free-text-then-parse output validation does not scale against
paraphrase variety; a typed-claims tool schema would close this properly. Net progress this
session, honestly counted: 3 real bugs found and fixed (entries 11, 12, 14), 2 phrasing gaps
in the same mechanism found, fixed, and superseded by further gaps (13's fix real but
incomplete), 1 gap deliberately left open with the correct fix identified but not built.

<!-- Template — copy per entry.

### N — one-line summary
**Asked:** 
**Answered:** 
**Wrong because:** 
**Class:** `retrieval` | `generation` | `corpus` | `framework`
**Fixed?** no — and why not

-->
