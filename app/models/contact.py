"""Contact form request models."""

import re
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

PHONE_PATTERN = re.compile(r"^[\d\s\-()]+$")


class ContactRequest(BaseModel):
    """Validated contact form submission."""

    name: Annotated[str, Field(min_length=2, max_length=100)]
    phone: Annotated[str, Field(min_length=7, max_length=20)]
    email: EmailStr
    comment: Annotated[str, Field(min_length=5, max_length=2000)]

    @field_validator("name", "phone", "email", "comment", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, value: str) -> str:
        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError(
                "Phone may contain only digits, spaces, parentheses, and dashes"
            )
        return value
