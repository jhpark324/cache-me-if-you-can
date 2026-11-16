import {
  MetadataList,
  MetadataListItem,
} from "@astryxdesign/core/MetadataList";
import type { Capture } from "./types";

const timestamp = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function formatted(value?: string) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : timestamp.format(date);
}

export function RecordDates({
  capture,
  isCurrent,
}: {
  capture: Capture;
  isCurrent: boolean;
}) {
  const saved = formatted(capture.created_at);
  const changedAt = isCurrent
    ? capture.updated_at
    : capture.revision_created_at;
  const changed = formatted(changedAt);
  if (!saved && !changed) return null;

  return (
    <MetadataList
      className="record-dates"
      orientation="horizontal"
      role="group"
      aria-label="기록 날짜"
    >
      {saved && (
        <MetadataListItem label="저장일">
          <time dateTime={capture.created_at}>{saved}</time>
        </MetadataListItem>
      )}
      {changed && changed !== saved && (
        <MetadataListItem label={isCurrent ? "최근 변경" : "이 저장본"}>
          <time dateTime={changedAt}>{changed}</time>
        </MetadataListItem>
      )}
    </MetadataList>
  );
}
