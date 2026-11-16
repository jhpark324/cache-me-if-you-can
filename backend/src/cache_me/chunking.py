"""Deterministic Markdown chunks with exact Python/Unicode source offsets."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Protocol

from markdown_it import MarkdownIt


class TokenCounter(Protocol):
    def count_tokens(self, text: str, kind: str = "document") -> int: ...


@dataclass(frozen=True)
class Section:
    body_start: int
    body_end: int
    header_path: list[str]


@dataclass(frozen=True)
class Chunk:
    body_start: int
    body_end: int
    text: str
    context_prefix: str
    context_truncated: bool
    section_refs: list[dict]
    split_reason: str

    @property
    def embedding_text(self) -> str:
        return self.context_prefix + self.text


class MarkdownChunker:
    def __init__(self, counter: TokenCounter, document_tokens: int = 512, overlap_tokens: int = 64):
        self.counter = counter
        self.document_tokens = document_tokens
        self.overlap_tokens = overlap_tokens
        self.parser = MarkdownIt("commonmark", {"html": False}).enable("table")

    def _fits(self, prefix: str, text: str, limit: int | None = None) -> bool:
        return self.counter.count_tokens(prefix + text) <= (limit or self.document_tokens)

    def _max_end(self, body: str, start: int, end: int, prefix: str, limit: int | None = None) -> int:
        lo, hi = start, end
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._fits(prefix, body[start:mid], limit):
                lo = mid
            else:
                hi = mid - 1
        while lo > start and not self._fits(prefix, body[start:lo], limit):
            lo -= 1
        return lo

    def _prefix(self, title: str | None, path: list[str]) -> tuple[str, bool]:
        parts = ([title] if title else []) + path
        original = " > ".join(parts) + "\n\n" if parts else ""
        if self._fits("", original, 64):
            return original, False
        chosen: list[str] = []
        # Nearby headings take precedence over ancestors, then the record title.
        for part in reversed(parts):
            candidate = " > ".join([part] + chosen) + "\n\n"
            if self._fits("", candidate, 64):
                chosen.insert(0, part)
            elif not chosen:
                end = self._max_end(part, 0, len(part), "", 60)
                if end:
                    chosen.append(part[:end])
        result = " > ".join(chosen) + "\n\n" if chosen else ""
        return result, result != original

    def _structure(self, body: str):
        offsets = [0]
        offsets.extend(match.end() for match in re.finditer(r"\r\n|\r|\n", body))
        if offsets[-1] != len(body):
            offsets.append(len(body))
        tokens = self.parser.parse(body)
        heading_starts: list[tuple[int, list[str], int]] = []
        stack: list[tuple[int, str]] = []
        blocks = []
        for i, token in enumerate(tokens):
            if token.map is None or token.level != 0 or token.nesting == -1:
                continue
            start = offsets[min(token.map[0], len(offsets) - 1)]
            end = offsets[min(token.map[1], len(offsets) - 1)]
            blocks.append((start, end, token.type))
            if token.type == "heading_open":
                level = int(token.tag[1:])
                heading = tokens[i + 1].content
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading))
                heading_starts.append((start, [value for _, value in stack], end))
        starts = [(0, [], 0)] if not heading_starts or heading_starts[0][0] else []
        starts.extend(heading_starts)
        sections = [Section(start, starts[i + 1][0] if i + 1 < len(starts) else len(body), path)
                    for i, (start, path, _) in enumerate(starts)]
        # A heading-only parent belongs with its first child, not in a lonely chunk.
        groups: list[list[Section]] = []
        join_next = False
        for i, section in enumerate(sections):
            heading_end = starts[i][2]
            only_heading = not body[heading_end:section.body_end].strip() and bool(section.header_path)
            if groups and join_next:
                groups[-1].append(section)
            else:
                groups.append([section])
            join_next = only_heading
        return sections, groups, blocks

    @staticmethod
    def _common_path(sections: list[Section]) -> list[str]:
        path = list(sections[0].header_path)
        for section in sections[1:]:
            while path != section.header_path[:len(path)]:
                path.pop()
        return path

    def split(self, body: str, title: str | None = None) -> list[Chunk]:
        if not body:
            return []
        sections, groups, blocks = self._structure(body)
        prefix, truncated = self._prefix(title, [])

        def make(start, end, chosen_prefix, context_truncated, reason):
            return Chunk(start, end, body[start:end], chosen_prefix, context_truncated,
                         [asdict(s) for s in sections if s.body_start < end and s.body_end > start], reason)

        if self._fits(prefix, body):
            return [make(0, len(body), prefix, truncated, "whole_record")]

        packed: list[list[Section]] = []
        for group in groups:
            previous = packed[-1] if packed else None
            if previous:
                left, right = previous[-1], group[0]
                siblings = left.header_path[:-1] == right.header_path[:-1] and len(left.header_path) == len(right.header_path)
                small = all(self.counter.count_tokens(body[s.body_start:s.body_end]) < 128 for s in previous + group)
                merged_prefix, _ = self._prefix(title, self._common_path(previous + group))
                if siblings and small and self._fits(merged_prefix, body[previous[0].body_start:group[-1].body_end]):
                    previous.extend(group)
                    continue
            packed.append(list(group))

        chunks: list[Chunk] = []
        for group in packed:
            start, end = group[0].body_start, group[-1].body_end
            prefix, truncated = self._prefix(title, self._common_path(group))
            if self._fits(prefix, body[start:end]):
                chunks.append(make(start, end, prefix, truncated, "packed_sections" if len(group) > 1 else "section"))
                continue
            boundaries = sorted({start, end, *(a for a, _, _ in blocks if start < a < end)})
            pending_start = start
            pending_end = start
            for left, right in zip(boundaries, boundaries[1:]):
                if self._fits(prefix, body[pending_start:right]):
                    pending_end = right
                    continue
                heading_prefix = pending_end > pending_start and all(
                    kind == "heading_open" for a, _, kind in blocks if pending_start <= a < left)
                if pending_end > pending_start and not heading_prefix:
                    chunks.append(make(pending_start, pending_end, prefix, truncated, "block"))
                forced_start = pending_start if heading_prefix else left
                pending_start = forced_start
                pending_end = left
                if self._fits(prefix, body[forced_start:right]):
                    pending_end = right
                    continue
                block_type = next((kind for a, _, kind in blocks if a == left), "paragraph_open")
                for a, b, reason in self._split_block(body, forced_start, right, prefix, block_type):
                    chunks.append(make(a, b, prefix, truncated, reason))
                pending_start = right
                pending_end = right
            if pending_end > pending_start:
                chunks.append(make(pending_start, pending_end, prefix, truncated, "block"))
        self._validate(body, chunks)
        return chunks

    def _split_block(self, body: str, start: int, end: int, prefix: str, kind: str):
        text = body[start:end]
        if kind in {"fence", "code_block", "table_open", "bullet_list_open", "ordered_list_open", "blockquote_open"}:
            boundaries = [start + m.end() for m in re.finditer(r"\r?\n", text)]
            reason = "block"
        else:
            code_spans = [m.span() for m in re.finditer(r"(`+)(.*?)\1", text, re.S)]
            boundaries = []
            for m in re.finditer(r"[.?!。？！](?:\s+|$)", text):
                if not any(a <= m.start() < b for a, b in code_spans):
                    # Decimal and URL-internal punctuation lack trailing whitespace.
                    boundaries.append(start + m.end())
            reason = "sentence"
        boundaries = sorted(set(boundaries + [end]))
        cursor = start
        frontier = start
        while frontier < end:
            fits = [b for b in boundaries if b > frontier and self._fits(prefix, body[cursor:b])]
            if fits:
                stop = max(fits)
                split_reason = reason
            else:
                stop = self._max_end(body, cursor, end, prefix)
                split_reason = "token"
            if stop <= frontier:
                cursor = frontier  # Reduce overlap before sacrificing forward progress.
                stop = self._max_end(body, cursor, end, prefix)
            if stop <= frontier:
                raise ValueError("Embedding context leaves no room for a source character")
            yield cursor, stop, split_reason
            frontier = stop
            if stop >= end:
                break
            # Prefer a complete sentence/line suffix within the overlap budget.
            suffixes = [b for b in [cursor] + boundaries if cursor < b < stop
                        and self._fits("", body[b:stop], self.overlap_tokens)]
            if suffixes:
                cursor = min(suffixes)
            else:
                lo, hi = cursor + 1, stop
                while lo < hi:
                    mid = (lo + hi) // 2
                    if self._fits("", body[mid:stop], self.overlap_tokens):
                        hi = mid
                    else:
                        lo = mid + 1
                cursor = lo

    def _validate(self, body: str, chunks: list[Chunk]):
        covered = 0
        for chunk in chunks:
            if chunk.body_start > covered or chunk.body_end <= covered:
                raise ValueError("Chunk coverage gap or no forward progress")
            if chunk.text != body[chunk.body_start:chunk.body_end] or not self._fits(chunk.context_prefix, chunk.text):
                raise ValueError("Invalid source span or embedding budget")
            covered = chunk.body_end
        if covered != len(body):
            raise ValueError("Incomplete source coverage")
