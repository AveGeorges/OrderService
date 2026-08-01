"""Errors from external Capashino services."""

from domain.exceptions import DomainError


class CatalogServiceError(DomainError):
    def __init__(self, message: str = "Catalog service unavailable") -> None:
        super().__init__(message)


class PaymentsServiceError(DomainError):
    def __init__(self, message: str = "Payments service unavailable") -> None:
        super().__init__(message)
