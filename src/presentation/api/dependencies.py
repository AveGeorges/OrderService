"""Dependency injection wiring — completed in stage 1."""

from collections.abc import Callable
from functools import lru_cache

from settings import Settings, get_settings


@lru_cache
def get_app_settings() -> Settings:
    return get_settings()


# Factories for use cases will be registered here in later stages.
DependencyFactory = Callable[..., object]
