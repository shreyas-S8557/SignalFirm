"""Phase 6 -- AI Outbound Messaging.

Fills the gap the architecture analysis called the single biggest one:
until this package existed, the pipeline could enrich and research a
company but a human had to write every outreach message from scratch. This
package generates the drafts (LinkedIn connection note, LinkedIn message,
cold-email A/B variants, a meeting-request draft, a call script, and a
follow-up sequence) -- it deliberately does NOT autonomously send LinkedIn
messages or connection requests, for the same reason `research/engine.py`
never fabricates a claim: automating LinkedIn actions violates LinkedIn's
Terms of Service and risks the account being restricted, and no amount of
code quality here changes that. See `send/linkedin_adapter.py` for exactly
what that module does instead (queues for manual send). Email sending has a
real SMTP adapter (`send/email_adapter.py`) that can optionally auto-send,
because a business's own transactional SMTP account sending its own email
is a completely different risk profile.

Module map:
- `models.py` -- data shapes (OutboundMessageSet, MessageVariant, etc).
- `prompts.py` / `generator.py` -- LLM call -> validated OutboundMessageSet,
  same "never let free-text drift reach a caller unvalidated" shape as
  `conversation/analyzer.py`.
- `engine.py` -- orchestration: gather company/person/research/ICP context,
  call the generator, persist the draft as a Note (reuses the existing Note
  object rather than adding a new Twenty custom object -- see that
  module's docstring for why).
- `sequence.py` -- SQLite-backed tracking of which follow-up step in a
  generated sequence is next due for a given person.
- `send/` -- adapters that actually deliver a single message on a given
  channel, used by `outbound_scheduler_main.py`'s daily sequence sweep.
"""
