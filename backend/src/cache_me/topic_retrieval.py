"""Conservative question-to-topic matching; no generated or semantic labels."""
from __future__ import annotations

import re

from .concept_labels import concept_label_key

TOPIC_LIMIT = 3
RECORDS_PER_TOPIC = 5

# A topic can be followed by a Korean particle, but not by an arbitrary word
# suffix (for example, the alias AI must not match inside "retail").
_PARTICLES = r"(?:에서|에게|으로|부터|까지|처럼|보다|하고|이랑|은|는|이|가|을|를|의|에|로|과|와|도|만|랑)"


def matched_topic_ids(query: str, concepts: list[dict]) -> list[str]:
    text = concept_label_key(query)
    owners: dict[str, set[str]] = {}
    for concept in concepts:
        for label in [concept["name"], *concept["aliases"]]:
            key = concept_label_key(label)
            if key:
                owners.setdefault(key, set()).add(concept["id"])

    matches = []
    for label, ids in owners.items():
        # Names and aliases never resolve ambiguous identities by recency.
        if len(ids) != 1:
            continue
        pattern = rf"(?<!\w){re.escape(label)}(?=$|\W|{_PARTICLES}(?=$|\W))"
        for match in re.finditer(pattern, text):
            matches.append((-len(label), match.start(), match.end(), next(iter(ids))))

    selected, spans = [], []
    for _, start, end, concept_id in sorted(matches):
        if concept_id in selected or any(start < right and end > left for left, right in spans):
            continue
        selected.append(concept_id)
        spans.append((start, end))
        if len(selected) >= TOPIC_LIMIT:
            break
    return selected
