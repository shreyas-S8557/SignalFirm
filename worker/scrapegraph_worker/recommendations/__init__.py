"""Recommendation Engine: turns the signals Conversation Intelligence has
already written onto Person/ConversationSignal records (see
`../conversation/`) into an every-morning digest -- who to contact, who to
ignore, hot vs. cold, highest buying intent, and a best-first message for
each.

No new LLM calls happen here. Interest level, urgency, sentiment, and
recommended next action are already-normalized enums by the time this
module sees them (`conversation/analyzer.py`'s whole job is to guarantee
that); this package's job is pure arithmetic and templating on top of that
known-safe data, plus Company.latestIcpScore/latestIcpPriority as an
optional bonus input for whenever a later milestone starts populating them
(see the top-level README's "What's NOT connected to anything yet").
"""
