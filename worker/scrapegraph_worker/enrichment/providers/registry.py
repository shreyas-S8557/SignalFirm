from __future__ import annotations

from ...config import DataProviderSettings
from .apollo import ApolloProvider
from .base import DataProvider
from .people_data_labs import PeopleDataLabsProvider


def build_providers(settings: DataProviderSettings) -> list[DataProvider]:
    """Returns configured providers in `settings.priority` order, skipping
    any with no API key set. Empty list (the default -- no keys
    configured) means enrichment behaves exactly as it did before this
    package existed.
    """
    available: dict[str, DataProvider] = {}
    if settings.apollo_api_key:
        available["apollo"] = ApolloProvider(settings.apollo_api_key, timeout_seconds=settings.timeout_seconds)
    if settings.people_data_labs_api_key:
        available["people_data_labs"] = PeopleDataLabsProvider(
            settings.people_data_labs_api_key, timeout_seconds=settings.timeout_seconds
        )
    return [available[name] for name in settings.priority if name in available]
