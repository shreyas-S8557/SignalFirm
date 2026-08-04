"""Channel-specific "actually deliver this one message" adapters.

Every adapter implements the same `SendAdapter` interface (see `base.py`)
so `sequence.py`'s daily sweep can dispatch a due step to whichever
adapter matches its `channel` without a big if/elif chain. Only
`email_adapter.py` can genuinely send something on its own; every other
channel's adapter reports back that it needs a human -- see each module's
own docstring for why that's a deliberate design choice here, not a
placeholder waiting to be filled in.
"""
