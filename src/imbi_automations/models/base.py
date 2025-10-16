"""Base models and common utilities for Pydantic models.

Provides base Pydantic model class with hashability and equality comparison
based on model content, used across all API response models.
"""

import json

import pydantic


class BaseModel(pydantic.BaseModel):
    """Base model with hash and equality support.

    Enables models to be used in sets and as dict keys by implementing
    __hash__ based on JSON serialization with sorted keys and __eq__ based
    on field values. Sorting keys ensures that two instances with identical
    content produce the same hash regardless of dict key insertion order.
    """

    def __hash__(self) -> int:
        return hash(json.dumps(self.model_dump(), sort_keys=True))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.model_dump() == other.model_dump()
