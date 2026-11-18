import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@astryxdesign/core/Button";
import { DialogHeader } from "@astryxdesign/core/Dialog";
import { Field } from "@astryxdesign/core/Field";
import { HStack } from "@astryxdesign/core/HStack";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import { Check, FileText, Plus, Search, X } from "lucide-react";
import { api, post, uid, errorText } from "./api";
import { Markdown } from "./Markdown";
import { ReferencePicker, type PickedReference } from "./RecordConnections";
import { sourceKey } from "./types";
import type {
  Capture,
  CaptureSummary,
  MutationResult,
  Page,
  SourceDetail,
  SourceRef,
} from "./types";
function useRequestId() {
  const current = useRef<{ key: string; id: string } | null>(null);
  return (payload: unknown) => {
    const key = JSON.stringify(payload);
    if (current.current?.key !== key) current.current = { key, id: uid() };
    return current.current.id;
  };
}
export function SourceReview({
  record,
  onSaved,
  onClose,
}: {
  record: Capture;
  onSaved: (result: MutationResult) => void;
  onClose: () => void;
}) {
  const [body, setBody] = useState(record.body_markdown),
    [reason, setReason] = useState(""),
    [sources, setSources] = useState(() =>
      record.sources.flatMap((s, i) => {
        // A provenance entry can back multiple independently editable citations.
        const numbers: (number | null)[] = (
          record.article?.citations ?? []
        ).flatMap((citation, index) =>
          citation.kind === "record" &&
          sourceKey(citation.source) === sourceKey(s.source)
            ? [index + 1]
            : [],
        );
        if (numbers.length === 0) numbers.push(null);
        return numbers.map((citationNumber) => ({
          ref: s.source,
          title: `기존 출처 ${i + 1}`,
          needsReview: s.review_state === "needs_review",
          citationNumber,
        }));
      }),
    ),
    [replacingNumber, setReplacingNumber] = useState<number | null>(null),
    [query, setQuery] = useState(""),
    [matches, setMatches] = useState<CaptureSummary[]>([]),
    [candidate, setCandidate] = useState<Capture | null>(null),
    [reference, setReference] = useState<SourceDetail | null>(null),
    [referenceLabel, setReferenceLabel] = useState(""),
    [busy, setBusy] = useState(false),
    [finding, setFinding] = useState(false),
    [error, setError] = useState("");
  const idFor = useRequestId(),
    lookupVersion = useRef(0);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setFinding(true);
      try {
        const result = await api<Page<CaptureSummary>>(
          "/captures?limit=20&query=" + encodeURIComponent(query),
        );
        if (active) setMatches(result.items.filter((r) => r.id !== record.id));
      } catch (e) {
        if (active) setError(errorText(e));
      } finally {
        if (active) setFinding(false);
      }
    }, 220);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, record.id]);
  async function preview(id: string) {
    const version = ++lookupVersion.current;
    setError("");
    setCandidate(null);
    setReference(null);
    setReferenceLabel("");
    try {
      const capture = await api<Capture>("/captures/" + id);
      if (version === lookupVersion.current) setCandidate(capture);
    } catch (e) {
      if (version === lookupVersion.current) setError(errorText(e));
    }
  }
  async function viewSource(ref: SourceRef, label: string) {
    const version = ++lookupVersion.current;
    setError("");
    setCandidate(null);
    setReference(null);
    setReferenceLabel(label);
    try {
      const detail = await post<SourceDetail>("/sources/resolve", ref);
      if (version === lookupVersion.current) setReference(detail);
    } catch (e) {
      if (version === lookupVersion.current) setError(errorText(e));
    }
  }
  function addCandidate() {
    if (!candidate) return;
    const ref = {
      capture_id: candidate.id,
      revision_id: candidate.revision_id,
    };
    setSources((prev) =>
      prev.some(
        (s) =>
          s.ref.capture_id === ref.capture_id &&
          s.ref.revision_id === ref.revision_id &&
          !s.ref.node_id &&
          s.ref.body_start == null,
      )
        ? prev
        : [
            ...prev,
            {
              ref,
              title: candidate.title || "제목 없는 기록",
              needsReview: false,
              citationNumber: null,
            },
          ],
    );
    setCandidate(null);
  }
  function replaceCitedSource(picked: PickedReference | null) {
    if (!picked || replacingNumber === null) return;
    setSources((prev) =>
      prev.map((item) =>
        item.citationNumber === replacingNumber
          ? {
              ...item,
              ref: picked.source,
              title: picked.capture.title || "제목 없는 기록",
              needsReview: false,
            }
          : item,
      ),
    );
    setReplacingNumber(null);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const article = record.article && {
      ...record.article,
      citations: [...record.article.citations],
    };
    if (article) {
      for (const item of sources) {
        if (item.citationNumber !== null) {
          article.citations[item.citationNumber - 1] = {
            kind: "record",
            source: item.ref,
          };
        }
      }
    }
    const payload = {
      capture_id: record.id,
      expected_revision_id: record.revision_id,
      expected_state_version: record.state_version,
      replacement_sources: [
        ...new Map(sources.map(({ ref }) => [sourceKey(ref), ref])).values(),
      ],
      review_reason: reason.trim(),
      body_markdown: body,
      ...(article ? { article } : {}),
    };
    try {
      const result = await post<MutationResult>(
        `/captures/${record.id}/source-review`,
        { ...payload, request_id: idFor(payload) },
      );
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <VStack gap={4}>
        <DialogHeader
          className="dialog-heading"
          title="출처 재검토"
          hasDivider={false}
          endContent={
            <IconButton
              className="app-icon-button"
              type="button"
              label="출처 재검토 닫기"
              tooltip="출처 재검토 닫기"
              icon={<X />}
              variant="ghost"
              onClick={onClose}
            />
          }
        />
        <Text as="p" type="supporting">
          {record.article
            ? "교체할 인용 번호를 고른 뒤 새 원문이나 구간을 선택하세요."
            : "현재 본문과 근거를 확인하고, 필요한 출처를 교체하거나 목록에서 제외하세요."}
        </Text>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Field label="기록 내용" inputID="source-review-body">
          <textarea
            id="source-review-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="body-editor review-body"
            required
          />
        </Field>
        <h3 className="management-heading">사용할 출처</h3>
        {!sources.length && (
          <p className="notice">
            연결할 출처가 없습니다. 근거 연결을 제거하는 이유를 아래에
            남겨주세요.
          </p>
        )}
        <VStack className="review-source-list" gap={2}>
          {sources.map((source, index) => {
            const numberLabel =
              source.citationNumber === null
                ? ""
                : `[${source.citationNumber}]`;
            return (
              <HStack
                className="review-source-row"
                key={numberLabel || sourceKey(source.ref)}
                gap={2}
                hAlign="between"
                vAlign="center"
              >
                <Button
                  label={
                    numberLabel
                      ? `${numberLabel} ${source.title}`
                      : source.title
                  }
                  type="button"
                  variant="ghost"
                  className="text-button"
                  icon={<FileText />}
                  onClick={() => void viewSource(source.ref, source.title)}
                />
                {record.article && source.needsReview && (
                  <Text type="supporting">교체 필요</Text>
                )}
                {numberLabel ? (
                  <Button
                    type="button"
                    variant="secondary"
                    label={`인용 ${numberLabel} 교체`}
                    onClick={() => setReplacingNumber(source.citationNumber)}
                  />
                ) : (
                  <IconButton
                    className="app-icon-button"
                    type="button"
                    label={`${source.title} 제외`}
                    tooltip={`${source.title} 제외`}
                    icon={<X />}
                    variant="ghost"
                    onClick={() =>
                      setSources((prev) => prev.filter((_, i) => i !== index))
                    }
                  />
                )}
              </HStack>
            );
          })}
        </VStack>
        {replacingNumber !== null && (
          <VStack gap={2}>
            <ReferencePicker
              key={replacingNumber}
              label={`인용 [${replacingNumber}]에 사용할 기록`}
              value={null}
              onChange={replaceCitedSource}
              excludeId={record.id}
            />
            <Button
              type="button"
              label="인용 교체 취소"
              variant="secondary"
              onClick={() => setReplacingNumber(null)}
            />
          </VStack>
        )}
        {reference && (
          <VStack as="section" className="reference-preview" gap={3}>
            <Text className="part-label" type="supporting">
              {referenceLabel} ·{" "}
              {reference.is_current ? "현재 저장본" : "당시 저장본"}
            </Text>
            <h4>{reference.capture.title || "제목 없는 기록"}</h4>
            <Markdown>{reference.text}</Markdown>
          </VStack>
        )}
        <details className="source-picker">
          <summary>다른 기록을 출처로 추가</summary>
          <VStack gap={3}>
            <TextInput
              label="기록 찾기"
              startIcon={Search}
              value={query}
              onChange={setQuery}
              placeholder="제목이나 내용으로 검색"
            />
            {finding && (
              <p role="status" className="muted">
                기록을 찾고 있어요
              </p>
            )}
            <VStack className="source-candidates" gap={2}>
              {matches.map((record) => (
                <Button
                  label={record.title || "제목 없는 기록"}
                  type="button"
                  variant="ghost"
                  key={record.id}
                  className="source-candidate"
                  onClick={() => void preview(record.id)}
                >
                  <VStack as="span" gap={1}>
                    <strong>{record.title || "제목 없는 기록"}</strong>
                    <Text type="supporting">{record.excerpt}</Text>
                  </VStack>
                </Button>
              ))}
            </VStack>
            {!finding && !matches.length && (
              <Text as="p" type="supporting">
                선택할 기록이 없습니다.
              </Text>
            )}
            {candidate && (
              <VStack as="section" className="reference-preview" gap={3}>
                <h4>{candidate.title || "제목 없는 기록"}</h4>
                {candidate.review_state === "needs_review" && (
                  <p className="notice">이 기록도 출처 재검토가 필요합니다.</p>
                )}
                <Markdown>{candidate.body_markdown}</Markdown>
                <Button
                  label="이 기록을 출처에 추가"
                  icon={<Plus />}
                  type="button"
                  variant="secondary"
                  onClick={addCandidate}
                  isDisabled={candidate.review_state === "needs_review"}
                />
              </VStack>
            )}
          </VStack>
        </details>
        <Field label="정정 이유" inputID="source-review-reason">
          <textarea
            id="source-review-reason"
            className="reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="어떤 근거를 확인했고 무엇을 바꾸었나요?"
            required
          />
        </Field>
        <HStack className="dialog-actions" gap={2} hAlign="end" wrap="wrap">
          <Button
            label="취소"
            type="button"
            variant="secondary"
            onClick={onClose}
            isDisabled={busy}
          />
          <Button
            label={busy ? "저장 중…" : "재검토 저장"}
            icon={<Check />}
            variant="primary"
            type="submit"
            isLoading={busy}
            isDisabled={
              busy ||
              !reason.trim() ||
              !body.trim() ||
              Boolean(record.article && sources.some((s) => s.needsReview))
            }
          />
        </HStack>
      </VStack>
    </form>
  );
}
