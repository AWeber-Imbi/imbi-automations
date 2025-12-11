"""Reusable validation mixins for workflow models.

These mixins encapsulate repeated validation patterns used across
workflow models in this project.

They are written to be compatible with Pydantic v2 and do not inherit
from BaseModel to avoid multiple BaseModel inheritance when used as
mixins. Pydantic will still pick up @model_validator methods from base
classes on the MRO.
"""

from __future__ import annotations

import dataclasses
import typing

import pydantic


class CommandRulesMixin:
    """Mixin for models with a command-like discriminator controlling
    field rules.

    Subclasses must provide:
      - command_field: the attribute name of the discriminator (e.g. 'command')
      - required_fields: mapping command value to set of required field names
      - allowed_fields: mapping command value to set of allowed field names
        (fields not in the set are considered forbidden when set)
      - validators: optional list of callables(model)->None for edge cases
    """

    command_field: typing.ClassVar[str]
    required_fields: typing.ClassVar[typing.Mapping[typing.Any, set[str]]] = {}
    allowed_fields: typing.ClassVar[typing.Mapping[typing.Any, set[str]]] = {}
    validators: typing.ClassVar[
        typing.Sequence[typing.Callable[[typing.Any], None]]
    ] = ()

    # Fields from WorkflowAction (and similar bases) that should never be
    # considered by command-specific allow/forbid checks.
    ignored_fields: typing.ClassVar[set[str]] = {
        'type',
        'name',
        'stage',
        'ai_commit',
        'commit_message',
        'conditions',
        'condition_type',
        'committable',
        'filter',
        'on_success',
        'on_failure',
        'timeout',
        'data',
    }

    # --- small helpers to reduce complexity and clarify intent ---
    def _cmd(self) -> typing.Any:
        return getattr(self, self.command_field)

    def _required_for(self, cmd: typing.Any) -> set[str]:
        return set(self.required_fields.get(cmd, set()))

    def _allowed_for(self, cmd: typing.Any) -> set[str]:
        return set(self.allowed_fields.get(cmd, set()))

    def _validate_required(self, cmd: typing.Any) -> None:
        for field in self._required_for(cmd):
            if getattr(self, field) is None:
                raise ValueError(
                    f"Field '{field}' is required for command '{cmd}'"
                )

    def _iter_model_field_names(self) -> typing.Iterable[str]:
        model_fields = getattr(self.__class__, 'model_fields', None)
        if model_fields is not None:
            return model_fields.keys()
        return (n for n in dir(self) if not n.startswith('_'))

    def _all_configured_fields(self) -> set[str]:
        names: set[str] = set()
        for fields in self.allowed_fields.values():
            names |= set(fields)
        for fields in self.required_fields.values():
            names |= set(fields)
        return names

    def _validate_forbidden(self, cmd: typing.Any) -> None:
        allowed = self._allowed_for(cmd)
        ignored = set(self.ignored_fields) | {self.command_field}
        configured_all = self._all_configured_fields()
        fields_set: set[str] = getattr(self, '__pydantic_fields_set__', set())
        for name in configured_all:
            if (
                name in ignored
                or name not in fields_set
                or getattr(self, name, None) is None
            ):
                continue
            if name not in allowed:
                raise ValueError(
                    f"Field '{name}' is not allowed for command '{cmd}'"
                )
        for name in self._iter_model_field_names():
            if (
                name in ignored
                or name in configured_all
                or name not in fields_set
                or getattr(self, name, None) is None
            ):
                continue
            if name not in allowed:
                raise ValueError(
                    f"Field '{name}' is not allowed for command '{cmd}'"
                )

    @pydantic.model_validator(mode='after')
    def _validate_by_command(self) -> typing.Self:
        cmd = self._cmd()
        self._validate_required(cmd)
        self._validate_forbidden(cmd)
        for fn in self.validators:
            fn(self)
        return self


@dataclasses.dataclass(frozen=True)
class Variant:
    name: str
    # fields that must be set (all must be non-None)
    requires_all: tuple[str, ...] = ()
    # if any of these are set, the corresponding partner(s) must also be set
    paired: tuple[
        tuple[str, str], ...
    ] = ()  # e.g. (("file_contains", "file"),)


class ExclusiveGroupsMixin:
    """Mixin for models where exactly one variant (group of fields) may be
    active.

    Subclasses must provide variants and may provide a second set for a
    "domain B" (e.g., local vs remote). When two domains are declared,
    the total active count across both must be exactly one.
    """

    variants_a: typing.ClassVar[typing.Sequence[Variant]] = ()
    variants_b: typing.ClassVar[typing.Sequence[Variant]] = ()  # optional

    def _active_count(self, variants: typing.Sequence[Variant]) -> int:
        count = 0
        for v in variants:
            for left, right in v.paired:
                left_set = getattr(self, left) is not None
                right_set = getattr(self, right) is not None
                if left_set and not right_set:
                    raise ValueError(f'{left} requires {right}')
            if v.requires_all and all(
                getattr(self, f) is not None for f in v.requires_all
            ):
                count += 1
        return count

    @pydantic.model_validator(mode='after')
    def _validate_exclusive_variants(self) -> typing.Self:
        a = self._active_count(self.variants_a)
        b = self._active_count(self.variants_b) if self.variants_b else 0
        total = a + b

        if total == 0:
            raise ValueError('At least one condition must be specified')
        if total > 1:
            raise ValueError(
                'Conditions are mutually exclusive - only one type allowed'
            )
        return self
