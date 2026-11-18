import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Network,
} from "lucide-react";
import { topicGroups } from "./graphTopics";
import type { GraphData, SourceRef } from "./types";

export default function TopicExplorer({
  data,
  selectedId,
  onSelect,
  onSource,
  onBrowse,
}: {
  data: GraphData;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onSource: (source: SourceRef) => void;
  onBrowse: (id: string) => void;
}) {
  const [open, setOpen] = useState(
    () => !window.matchMedia("(max-width: 800px)").matches,
  );
  const [query, setQuery] = useState("");
  const contentId = useId();
  const panel = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const groups = useMemo(
    () =>
      topicGroups(data).sort(
        (a, b) =>
          b.records.length - a.records.length ||
          (a.node.label || a.node.name || "").localeCompare(
            b.node.label || b.node.name || "",
            "ko",
          ),
      ),
    [data],
  );
  const selected = groups.find((group) => group.node.id === selectedId);
  const normalized = query.normalize("NFKC").toLocaleLowerCase().trim();
  const visible = groups.filter(({ node }) =>
    (node.label || node.name || "")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .includes(normalized),
  );
  useEffect(() => {
    if (!selectedId) return;
    setOpen(true);
  }, [selectedId]);
  useEffect(() => {
    if (!selectedId || !open) return;
    const frame = requestAnimationFrame(() => heading.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [selectedId, open]);
  function clearSelection() {
    onSelect(null);
    requestAnimationFrame(() => panel.current?.querySelector("input")?.focus());
  }
  if (!groups.length) return null;
  return (
    <section
      ref={panel}
      className="topic-explorer"
      aria-label="주제로 살펴보기"
      data-open={open}
      onKeyDownCapture={(event) => {
        if (event.key !== "Escape" || !open) return;
        event.preventDefault();
        event.stopPropagation();
        if (selected) clearSelection();
        else {
          setOpen(false);
          trigger.current?.focus();
        }
      }}
    >
      <Button
        ref={trigger}
        className="topic-explorer-toggle"
        variant="ghost"
        size="sm"
        width="100%"
        label="주제로 살펴보기"
        icon={<Network />}
        endContent={open ? <ChevronUp /> : <ChevronDown />}
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen(!open)}
      />
      {open && (
        <VStack id={contentId} className="topic-explorer-content" gap={2}>
          {selected ? (
            <>
              <Button
                className="topic-back"
                variant="ghost"
                size="sm"
                label="전체 연결 보기"
                icon={<ArrowLeft />}
                onClick={clearSelection}
              />
              <Heading
                level={3}
                ref={heading}
                tabIndex={-1}
                className="topic-selected-heading"
              >
                {selected.node.label || selected.node.name || "주제"}
              </Heading>
              <Text
                type="inherit"
                color="inherit"
                className="topic-scope"
                role="status"
              >
                이 화면의 연결 기록 {selected.records.length}개
              </Text>
              <VStack
                className="topic-rows"
                gap={1}
                aria-label="주제에 연결된 기록"
              >
                {selected.records.map((record) => (
                  <Button
                    key={record.id}
                    className="topic-record-open"
                    variant="ghost"
                    size="sm"
                    width="100%"
                    label={`${record.label} 출처 보기`}
                    onClick={() => onSource(record.source)}
                  >
                    <Text
                      type="inherit"
                      color="inherit"
                      className="topic-record-title"
                      maxLines={2}
                      hasTruncateTooltip={false}
                    >
                      {record.label}
                    </Text>
                    <Text
                      type="inherit"
                      color="inherit"
                      className="topic-record-via"
                      display="block"
                    >
                      {record.via === "both"
                        ? "기록과 세부 항목의 주제"
                        : record.via === "node"
                          ? "세부 항목의 주제"
                          : "기록의 주제"}
                    </Text>
                  </Button>
                ))}
                {!selected.records.length && (
                  <Text type="inherit" color="inherit" className="topic-scope">
                    표시된 연결 기록이 없어요.
                  </Text>
                )}
              </VStack>
              <Button
                className="topic-browse"
                variant="secondary"
                size="sm"
                label="이 주제의 모든 기록"
                icon={<ArrowUpRight />}
                onClick={() =>
                  onBrowse(
                    selected.node.concept_id ||
                      selected.node.id.replace(/^concept:/, ""),
                  )
                }
              />
            </>
          ) : (
            <>
              <Text type="inherit" color="inherit" className="topic-scope">
                주제를 선택하면 연결된 기록을 강조해요.
              </Text>
              <TextInput
                type="search"
                label="주제 이름 찾기"
                isLabelHidden
                placeholder="주제 이름 찾기"
                value={query}
                onChange={setQuery}
                hasClear
                size="sm"
                width="100%"
              />
              <VStack className="topic-rows" gap={1} aria-label="표시된 주제">
                {visible.map((group) => (
                  <Button
                    key={group.node.id}
                    className="topic-choice"
                    variant="ghost"
                    size="sm"
                    width="100%"
                    label={`${group.node.label || group.node.name || "주제"}, 연결 기록 ${group.records.length}개`}
                    onClick={() => onSelect(group.node.id)}
                  >
                    <Text
                      type="inherit"
                      color="inherit"
                      className="topic-choice-name"
                    >
                      {group.node.label || group.node.name || "주제"}
                    </Text>
                    <Text
                      type="inherit"
                      color="inherit"
                      className="topic-choice-count"
                    >
                      {group.records.length}
                    </Text>
                  </Button>
                ))}
                {!visible.length && (
                  <Text type="inherit" color="inherit" className="topic-scope">
                    일치하는 주제가 없어요.
                  </Text>
                )}
              </VStack>
              <Text
                type="inherit"
                color="inherit"
                className="topic-scope topic-count-note"
              >
                개수는 이 화면에 표시된 연결 기준입니다.
              </Text>
            </>
          )}
          {data.truncated && (
            <Text type="inherit" color="inherit" className="topic-scope">
              연결의 일부를 표시하고 있어요.
            </Text>
          )}
        </VStack>
      )}
    </section>
  );
}
