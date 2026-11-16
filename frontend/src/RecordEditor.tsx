import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Field } from "@astryxdesign/core/Field";
import { HStack } from "@astryxdesign/core/HStack";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import { Check, X } from "lucide-react";
import { api, errorText, uid } from "./api";
import { Markdown } from "./Markdown";
import {
  KIND_LABELS,
  type Capture,
  type MutationResult,
  type RecordKind,
  type SourceRef,
} from "./types";

const kinds = Object.entries(KIND_LABELS) as [RecordKind, string][];

export default function RecordEditor({
  record,
  body,
  sources,
  onSaved,
  onClose,
}: {
  record?: Capture;
  body?: string;
  sources?: SourceRef[];
  onSaved: (result: MutationResult) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(record?.title || ""),
    [content, setContent] = useState(record?.body_markdown || body || ""),
    [selectedKinds, setKinds] = useState<RecordKind[]>(record?.kinds || []),
    [visibility, setVisibility] = useState<"public" | "private">(
      record?.visibility || "public",
    ),
    [completion, setCompletion] = useState(record?.completion_state || ""),
    [hints, setHints] = useState(record?.concept_hints.join(", ") || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [preview, setPreview] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const titleInput = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  );
  const saved = useRef(false);
  const resumeFocus = useRef<HTMLElement | null>(null);
  const editorForm = useRef<HTMLFormElement>(null);
  const busyRef = useRef(false);
  useEffect(() => {
    // Astryx first focuses its dialog heading; the editor starts at the title
    // field once the native dialog has opened.
    const frame = requestAnimationFrame(() => titleInput.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(
    () => () => {
      // Wait for native dialog cleanup, but leave saved-record navigation and
      // StrictMode's still-mounted form in control of focus.
      requestAnimationFrame(() => {
        if (saved.current || editorForm.current?.isConnected) return;
        const target =
          opener.current?.isConnected &&
          !opener.current.closest("dialog:not([open])")
            ? opener.current
            : document.getElementById("main");
        target?.focus();
      });
    },
    [],
  );
  function changeDiscard(open: boolean) {
    setConfirmDiscard(open);
    if (!open)
      requestAnimationFrame(() => {
        if (resumeFocus.current?.isConnected) resumeFocus.current.focus();
      });
  }
  const initial = useRef({
    title: record?.title || "",
    content: record?.body_markdown || "",
    selectedKinds: [...(record?.kinds || [])].sort(),
    visibility: record?.visibility || "public",
    completion: record?.completion_state || "",
    hints: record?.concept_hints.join(", ") || "",
  });
  // Prefilled answers are unsaved drafts too: a new record compares against
  // an empty draft, while edits compare against the persisted record.
  const dirty =
    JSON.stringify({
      title,
      content,
      selectedKinds: [...selectedKinds].sort(),
      visibility,
      completion,
      hints,
    }) !== JSON.stringify(initial.current) ||
    (!record && !!sources?.length);
  function requestClose() {
    if (busyRef.current || confirmDiscard) return;
    if (!dirty) return onClose();
    resumeFocus.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : titleInput.current;
    setConfirmDiscard(true);
  }
  const requestRef = useRef<{ fingerprint: string; id: string } | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (busyRef.current || confirmDiscard) return;
    if (!content.trim()) {
      setError("기록할 내용을 입력해 주세요.");
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError("");
    const values = {
      title: title.trim() || null,
      body_markdown: content,
      kinds: selectedKinds,
      visibility,
      completion_state: completion || null,
      concept_hints: hints
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    };
    const changes = record
      ? Object.fromEntries(
          Object.entries(values).filter(
            ([key, value]) =>
              JSON.stringify(record[key as keyof Capture] ?? null) !==
              JSON.stringify(value),
          ),
        )
      : values;
    if (record && !Object.keys(changes).length) {
      busyRef.current = false;
      setBusy(false);
      onClose();
      return;
    }
    const payload = record
      ? {
          capture_id: record.id,
          expected_revision_id: record.revision_id,
          expected_state_version: record.state_version,
          changes,
        }
      : { ...values, sources: sources || [] };
    const fingerprint = JSON.stringify(payload);
    if (requestRef.current?.fingerprint !== fingerprint)
      requestRef.current = { fingerprint, id: uid() };
    try {
      const result = await api<MutationResult>(
        record ? `/captures/${record.id}` : "/captures",
        {
          method: record ? "PATCH" : "POST",
          body: JSON.stringify({
            ...payload,
            request_id: requestRef.current.id,
          }),
        },
      );
      saved.current = true;
      onSaved(result);
    } catch (e) {
      saved.current = false;
      setError(errorText(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <Dialog
        isOpen
        purpose="info"
        width="min(48rem, calc(100vw - var(--spacing-6)))"
        maxHeight="90dvh"
        className="editor-dialog"
        aria-busy={busy}
        onOpenChange={(open) => {
          if (!open) requestClose();
        }}
      >
        <form
          ref={editorForm}
          onSubmit={save}
          onKeyDown={(event) => {
            if (
              (event.ctrlKey || event.metaKey) &&
              event.key === "Enter" &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              if (!busyRef.current && !confirmDiscard)
                event.currentTarget.requestSubmit();
            }
          }}
        >
          <VStack gap={4}>
            <DialogHeader
              className="dialog-heading"
              title={record ? "기록 수정" : "새 기록"}
              hasDivider={false}
              endContent={
                <IconButton
                  className="app-icon-button"
                  type="button"
                  label="편집 닫기"
                  tooltip="편집 닫기"
                  icon={<X aria-hidden="true" />}
                  variant="ghost"
                  onClick={requestClose}
                  isDisabled={busy}
                />
              }
            />
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <TextInput
              ref={titleInput}
              label="제목 선택"
              isDisabled={busy}
              hasAutoFocus
              data-editor-title
              value={title}
              onChange={setTitle}
              placeholder="이 생각에 이름을 붙여보세요"
            />
            <VStack gap={2}>
              <HStack
                className="section-heading"
                hAlign="between"
                vAlign="center"
                gap={2}
              >
                <Text type="label">내용</Text>
                <Button
                  label={preview ? "편집하기" : "미리 보기"}
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setPreview(!preview)}
                  isDisabled={busy}
                />
              </HStack>
              {preview ? (
                <VStack className="editor-preview">
                  <Markdown>{content || "아직 내용이 없습니다."}</Markdown>
                </VStack>
              ) : (
                <Field
                  label="내용"
                  inputID="record-body"
                  isLabelHidden
                  isDisabled={busy}
                >
                  <textarea
                    id="record-body"
                    disabled={busy}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="기억하고 싶은 내용을 적어주세요. Markdown을 사용할 수 있어요."
                    className="body-editor"
                    required
                  />
                </Field>
              )}
            </VStack>
            <details className="editor-options">
              <summary>유형과 공개 범위</summary>
              <VStack gap={4}>
                <fieldset>
                  <legend>기록 유형</legend>
                  <HStack className="kind-options" gap={3} wrap="wrap">
                    {kinds.map(([kind, label]) => (
                      <CheckboxInput
                        key={kind}
                        label={label}
                        isDisabled={busy}
                        value={selectedKinds.includes(kind)}
                        onChange={(checked) =>
                          setKinds((previous) =>
                            checked
                              ? [...previous, kind]
                              : previous.filter((value) => value !== kind),
                          )
                        }
                      />
                    ))}
                  </HStack>
                </fieldset>
                <HStack
                  className="field-row"
                  gap={4}
                  wrap="wrap"
                  vAlign="start"
                >
                  <Field
                    label="공개 범위"
                    inputID="record-visibility"
                    description="현재는 내 기기에서만 사용합니다."
                    descriptionID="visibility-hint"
                    isDisabled={busy}
                  >
                    <select
                      id="record-visibility"
                      aria-describedby="visibility-hint"
                      disabled={busy}
                      value={visibility}
                      onChange={(e) =>
                        setVisibility(e.target.value as "public" | "private")
                      }
                    >
                      <option value="public">공개</option>
                      <option value="private">비공개</option>
                    </select>
                  </Field>
                  <Field
                    label="완료 상태"
                    inputID="record-completion"
                    isDisabled={busy}
                  >
                    <select
                      id="record-completion"
                      disabled={busy}
                      value={completion}
                      onChange={(e) => setCompletion(e.target.value)}
                    >
                      <option value="">해당 없음</option>
                      <option value="incomplete">미완료</option>
                      <option value="completed">완료</option>
                    </select>
                  </Field>
                </HStack>
                <TextInput
                  label="주제 힌트"
                  isDisabled={busy}
                  value={hints}
                  onChange={setHints}
                  placeholder="학습, 데이터베이스"
                  description="쉼표로 구분합니다. 저장 후 주제를 연결합니다."
                />
              </VStack>
            </details>
            {sources?.length ? (
              <Text as="p" type="supporting">
                참조한 출처 {sources.length}개를 함께 저장합니다.
              </Text>
            ) : null}
            <HStack className="dialog-actions" hAlign="end" gap={2} wrap="wrap">
              <Button
                label="취소"
                variant="secondary"
                type="button"
                onClick={requestClose}
                isDisabled={busy}
              />
              <Button
                label={busy ? "저장 중…" : "저장"}
                icon={<Check aria-hidden="true" />}
                variant="primary"
                type="submit"
                isLoading={busy}
                isDisabled={busy || !content.trim()}
              />
            </HStack>
          </VStack>
        </form>
      </Dialog>
      <AlertDialog
        isOpen={confirmDiscard}
        onOpenChange={changeDiscard}
        title="작성 중인 내용을 버릴까요?"
        description="저장하지 않은 변경 내용이 사라집니다."
        cancelLabel="계속 작성"
        actionLabel="버리기"
        onAction={() => {
          if (!busyRef.current) onClose();
        }}
      />
    </>
  );
}
