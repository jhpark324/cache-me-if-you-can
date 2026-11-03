import { useRef, useState, type FormEvent } from "react";
import { AlertDialog, Button, Dialog, IconButton } from "@radix-ui/themes";
import { Check, LoaderCircle, X } from "lucide-react";
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
  const cancelDiscard = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
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
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) requestClose();
      }}
    >
      <Dialog.Content
        className="editor-dialog"
        aria-describedby={undefined}
        aria-busy={busy}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          titleInput.current?.focus();
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          // Saving navigates to the record heading in App. Cancel/discard
          // returns to the opener, including a replacement for a closed menu.
          if (!saved.current) {
            const target =
              opener.current?.isConnected &&
              !opener.current.closest('[role="dialog"][data-state="closed"]')
                ? opener.current
                : document.getElementById("create-record");
            target?.focus();
          }
        }}
        onEscapeKeyDown={(event) => {
          if (busyRef.current || confirmDiscard) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          if (busyRef.current || confirmDiscard) event.preventDefault();
        }}
      >
        <form
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
          <div className="panel-heading">
            <Dialog.Title>{record ? "기록 수정" : "새 기록"}</Dialog.Title>
            <IconButton
              type="button"
              aria-label="편집 닫기"
              title="편집 닫기"
              variant="ghost"
              onClick={requestClose}
              disabled={busy}
            >
              <X aria-hidden="true" />
            </IconButton>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <label className="field">
            제목 <span className="optional">선택</span>
            <input
              ref={titleInput}
              disabled={busy}
              data-editor-title
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="이 생각에 이름을 붙여보세요"
            />
          </label>
          <div className="section-heading">
            <label htmlFor="record-body">내용</label>
            <button
              type="button"
              className="text-button"
              onClick={() => setPreview(!preview)}
              disabled={busy}
            >
              {preview ? "편집하기" : "미리 보기"}
            </button>
          </div>
          {preview ? (
            <div className="editor-preview">
              <Markdown>{content || "아직 내용이 없습니다."}</Markdown>
            </div>
          ) : (
            <textarea
              id="record-body"
              disabled={busy}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="기억하고 싶은 내용을 적어주세요. Markdown을 사용할 수 있어요."
              className="body-editor"
              required
            />
          )}
          <details className="editor-options">
            <summary>유형과 공개 범위</summary>
            <fieldset>
              <legend>기록 유형</legend>
              <div className="kind-options">
                {kinds.map(([k, l]) => (
                  <label
                    key={k}
                    className={`kind-option ${selectedKinds.includes(k) ? "checked" : ""}`}
                  >
                    <input
                      type="checkbox"
                      disabled={busy}
                      checked={selectedKinds.includes(k)}
                      onChange={(e) =>
                        setKinds((prev) =>
                          e.target.checked
                            ? [...prev, k]
                            : prev.filter((x) => x !== k),
                        )
                      }
                    />
                    {l}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="field-row">
              <label className="field">
                공개 범위
                <select
                  disabled={busy}
                  value={visibility}
                  onChange={(e) =>
                    setVisibility(e.target.value as "public" | "private")
                  }
                >
                  <option value="public">공개</option>
                  <option value="private">비공개</option>
                </select>
                <span className="field-hint">
                  현재는 내 기기에서만 사용합니다.
                </span>
              </label>
              <label className="field">
                완료 상태
                <select
                  disabled={busy}
                  value={completion}
                  onChange={(e) => setCompletion(e.target.value)}
                >
                  <option value="">해당 없음</option>
                  <option value="incomplete">미완료</option>
                  <option value="completed">완료</option>
                </select>
              </label>
            </div>
            <label className="field">
              주제 힌트
              <input
                disabled={busy}
                value={hints}
                onChange={(e) => setHints(e.target.value)}
                placeholder="학습, 데이터베이스"
              />
              <span className="field-hint">
                쉼표로 구분합니다. 저장 후 주제를 연결합니다.
              </span>
            </label>
          </details>
          {sources?.length ? (
            <p className="muted">
              참조한 출처 {sources.length}개를 함께 저장합니다.
            </p>
          ) : null}
          <div className="dialog-actions">
            <Button
              variant="soft"
              color="gray"
              type="button"
              onClick={requestClose}
              disabled={busy}
            >
              취소
            </Button>
            <Button type="submit" disabled={busy || !content.trim()}>
              {busy ? (
                <LoaderCircle className="spin" aria-hidden="true" />
              ) : (
                <Check aria-hidden="true" />
              )}
              {busy ? "저장 중…" : "저장"}
            </Button>
          </div>
        </form>
        <AlertDialog.Root
          open={confirmDiscard}
          onOpenChange={setConfirmDiscard}
        >
          <AlertDialog.Content
            className="confirm-dialog"
            onOpenAutoFocus={(event) => {
              event.preventDefault();
              cancelDiscard.current?.focus();
            }}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              if (resumeFocus.current?.isConnected) resumeFocus.current.focus();
            }}
            onEscapeKeyDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
              event.stopImmediatePropagation();
              setConfirmDiscard(false);
            }}
            onKeyDown={(event) => {
              // Handle rapid reopen/escape while the primitive's document
              // listener is changing layers during its exit animation.
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                setConfirmDiscard(false);
              }
            }}
          >
            <AlertDialog.Title>작성 중인 내용을 버릴까요?</AlertDialog.Title>
            <AlertDialog.Description>
              저장하지 않은 변경 내용이 사라집니다.
            </AlertDialog.Description>
            <div className="dialog-actions">
              <AlertDialog.Cancel>
                <Button
                  ref={cancelDiscard}
                  type="button"
                  variant="soft"
                  color="gray"
                >
                  계속 작성
                </Button>
              </AlertDialog.Cancel>
              <Button
                type="button"
                color="red"
                onClick={() => {
                  if (!busyRef.current) onClose();
                }}
              >
                버리기
              </Button>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Root>
      </Dialog.Content>
    </Dialog.Root>
  );
}
