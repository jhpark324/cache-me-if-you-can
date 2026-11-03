"""Public record types and interpretation of immutable historical classifications."""
from typing import Annotated, Literal, get_args

from pydantic import BeforeValidator

RecordKind = Literal["knowledge", "episode", "context", "idea", "decision", "artifact"]
RECORD_KINDS = frozenset(get_args(RecordKind))
LEGACY_KIND_ALIASES = {"procedure": "knowledge", "reflection": "episode", "plan": "idea"}


def normalize_record_kinds(values):
    """Collapse aliases without inferring types from the body or rewriting history."""
    if not isinstance(values, (list, tuple, set, frozenset)):
        return values  # Let the enclosing Pydantic list validator reject bad input.
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("record kinds must be strings")
        kind = LEGACY_KIND_ALIASES.get(value, value)
        if kind not in RECORD_KINDS:
            raise ValueError("unknown record kind")
        if kind not in result:
            result.append(kind)
    return result


# The JSON schema advertises only the six current types. Older clients can still
# submit aliases, including combinations that now mean the same classification.
RecordKinds = Annotated[list[RecordKind], BeforeValidator(normalize_record_kinds)]


def storage_kinds_for_filter(values):
    """Match both new values and historical rows, without a revision migration."""
    selected = set(normalize_record_kinds(values))
    return sorted(selected | {alias for alias, kind in LEGACY_KIND_ALIASES.items() if kind in selected})
