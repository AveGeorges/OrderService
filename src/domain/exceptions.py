class DomainError(Exception):
    """Base domain exception."""


class OrderNotFoundError(DomainError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")


class InsufficientStockError(DomainError):
    def __init__(self, item_id: str, requested: int, available: int) -> None:
        self.item_id = item_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for item {item_id}: "
            f"requested={requested}, available={available}",
        )


class ItemNotFoundError(DomainError):
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"Item not found: {item_id}")


class InvalidOrderStateError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
