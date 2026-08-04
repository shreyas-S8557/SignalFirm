from __future__ import annotations

import abc
from typing import Optional

from .models import ProviderCompanyProfile


class DataProvider(abc.ABC):
    """One implementation per vendor. `lookup_company` must never raise --
    a provider outage, a 404 (no match), or a response shape the adapter
    doesn't recognize should all just come back as `None`, so a single
    flaky/rate-limited provider can never take down an enrichment run.
    """

    name: str

    @abc.abstractmethod
    def lookup_company(self, domain: str) -> Optional[ProviderCompanyProfile]:
        raise NotImplementedError
