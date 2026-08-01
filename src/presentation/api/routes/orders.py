from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from application.usecases.create_order import CreateOrder, CreateOrderCommand
from application.usecases.get_order import GetOrder
from application.usecases.process_payment_callback import (
    PaymentCallbackCommand,
    ProcessPaymentCallback,
)
from presentation.api.dependencies import (
    get_create_order_use_case,
    get_get_order_use_case,
    get_process_payment_callback_use_case,
)
from presentation.api.schemas import (
    OrderCreateRequest,
    OrderResponse,
    PaymentCallbackRequest,
    order_to_response,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

CreateOrderUseCase = Annotated[CreateOrder, Depends(get_create_order_use_case)]
GetOrderUseCase = Annotated[GetOrder, Depends(get_get_order_use_case)]
ProcessPaymentCallbackUseCase = Annotated[
    ProcessPaymentCallback,
    Depends(get_process_payment_callback_use_case),
]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderResponse)
async def create_order(
    body: OrderCreateRequest,
    use_case: CreateOrderUseCase,
) -> OrderResponse:
    order = await use_case(
        CreateOrderCommand(
            user_id=body.user_id,
            item_id=body.item_id,
            quantity=body.quantity,
            idempotency_key=body.idempotency_key,
        ),
    )
    return order_to_response(order)


@router.post("/payment-callback", status_code=status.HTTP_200_OK)
async def payment_callback(
    body: PaymentCallbackRequest,
    use_case: ProcessPaymentCallbackUseCase,
) -> dict[str, str]:
    await use_case(
        PaymentCallbackCommand(
            payment_id=body.payment_id,
            order_id=body.order_id,
            status=body.status,
            amount=body.amount,
            error_message=body.error_message,
        ),
    )
    return {"status": "ok"}


@router.get("/{order_id}", status_code=status.HTTP_200_OK, response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    use_case: GetOrderUseCase,
) -> OrderResponse:
    order = await use_case(order_id)
    return order_to_response(order)
