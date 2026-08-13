import asyncio

from transloka_translation.providers import (
    FakeTranslationProvider,
    LocalModel,
    ProviderHealthStatus,
    TranslationProvider,
)


def test_fake_provider_satisfies_runtime_provider_contract() -> None:
    provider = FakeTranslationProvider[str, str](response="translated")

    assert isinstance(provider, TranslationProvider)


def test_provider_health_and_model_listing_are_normalized_and_isolated() -> None:
    model = LocalModel(name="local-model", size_bytes=1024)
    provider = FakeTranslationProvider[str, str](response="translated", models=[model])

    health = asyncio.run(provider.health_check())
    first_listing = asyncio.run(provider.list_models())
    first_listing.clear()

    assert health.status is ProviderHealthStatus.AVAILABLE
    assert health.version == "fake"
    assert asyncio.run(provider.list_models()) == [model]
