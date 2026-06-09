from typing import Literal
from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


PaymentMethod = Literal[
    "cash",
    "pix",
    "card",
    "credit",
    "debit",
    "external",
    "pending",
]


StockMovementType = Literal[
    "in",
    "out",
    "adjustment",
]