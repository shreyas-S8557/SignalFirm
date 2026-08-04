"""Phase 5: Research Automation.

Takes the raw material Phase 4 enrichment gathered (crawled site text,
detected tech stack, hiring/buying keyword hits) and turns it into the
sales-facing read a rep actually needs before first contact: what this
company does, what problems they plausibly have, and what angle to open
with.

  models.py   -- ResearchResult and its sub-models
  prompts.py  -- the system prompt (one place that pins the JSON contract)
  agent.py    -- LLM call + parsing/normalization, no I/O to Twenty
  engine.py   -- orchestration: read EnrichmentJob -> run agent -> write
                 one ResearchJob record (status RESEARCHED / RESEARCH_FAILED)

**The central honesty constraint of this module.** Enrichment deals in
observations ("this string appeared on this page"). Research necessarily
deals in inference, and inference about a company you've never spoken to
is exactly where an LLM will happily invent a confident, specific,
plausible falsehood -- and here that falsehood would be attached to a real
company's CRM record and read by a rep about to contact them. So:

* Every research run is **grounded**: it reads from a specific
  EnrichmentJob record and can't run at all without one (see
  `engine.py`'s NoEnrichmentDataError). No enrichment, no research --
  rather than letting the model free-associate from a company name.
* Pain points and sales angles are **labelled hypotheses everywhere they
  appear** -- in the prompt, in the models, in the Twenty field
  descriptions, and in the rendered output -- because they are the two
  fields most likely to be mistaken for researched fact.
* Every item must cite what it was derived from (`derived_from`), and
  items that don't are dropped in normalization rather than passed
  through uncited.
* `confidence` is computed deterministically from how much grounding
  material the run actually had, never read from the LLM's own
  self-assessment (same rule as `enrichment/engine.py::_score_result` and
  `ICPScore.score`).
"""
