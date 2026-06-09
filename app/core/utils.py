from decimal import Decimal
from uuid import UUID
from datetime import datetime, date


def serialize_row(row: dict) -> dict:
    output = {}

    for key, value in row.items():
        if isinstance(value, UUID):
            output[key] = str(value)
        elif isinstance(value, Decimal):
            output[key] = float(value)
        elif isinstance(value, datetime | date):
            output[key] = value.isoformat()
        else:
            output[key] = value

    return output