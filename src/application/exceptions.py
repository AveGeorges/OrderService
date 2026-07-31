"""Catalog Service errors beyond domain stock/not-found cases."""

from domain.exceptions import DomainError


class CatalogServiceError(DomainError):
    def __init__(self, message: str = "Catalog service unavailable") -> None:
        super().__init__(message)
