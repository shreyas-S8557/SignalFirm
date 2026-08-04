"""ICP (Ideal Customer Profile) Scoring.

Fills the gap `workflow/derive.py` used to call BLOCKED_ON_ICP_SCORING:
`rubric.py` is a pure, deterministic weighted-scoring function (no network,
no LLM -- same "arithmetic on known-safe categories" shape as
`recommendations/scorer.py`), and `engine.py` is the orchestration that
reads a company's latest EnrichmentJob/ResearchJob, scores it, and writes
one ICPScore record (the object was already scaffolded in
twenty-app/src/objects/icp-score.object.ts -- this is the first code that
writes to it).

Deliberately NOT LLM-based: an ICP fit score is a fact about how well a
company matches a rubric the business defines, not something to ask a
model to guess at. The rubric itself (weights + target lists) lives in
`data/icp_rubric.yaml` so it can be tuned without a code change, with
`RUBRIC_VERSION` bumped whenever the shape of the weights changes, so a
score is always traceable to the exact rubric that produced it.
"""
