import { type ReactNode, useId, useMemo } from "react";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";

type Mode = "grouped" | "stacked";

interface Datum {
  series: string;
  index: number;
  value: number;
  display: string;
}

interface Group {
  label: string;
  values: Datum[];
  total: number;
}

interface Chart {
  title: string;
  mode: Mode;
  unit: string;
  groups: Group[];
  maximum: number;
}

const fractionPercent = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 2,
});

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isLabel(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function datum(
  input: unknown,
  series: string,
  index: number,
  unit: string,
  mode: Mode,
): Datum | null {
  if (typeof input === "number") {
    if (!Number.isFinite(input) || input < 0 || (unit === "%" && input > 100))
      return null;
    return { series, index, value: input, display: `${input}${unit}` };
  }
  if (mode !== "grouped" || unit !== "%" || !isObject(input)) return null;
  const { part, total } = input;
  if (
    typeof part !== "number" ||
    typeof total !== "number" ||
    !Number.isSafeInteger(part) ||
    !Number.isSafeInteger(total) ||
    total <= 0 ||
    part < 0 ||
    part > total
  )
    return null;
  const value = (part / total) * 100;
  let percent = fractionPercent.format(value);
  if (part > 0 && percent === "0") percent = "<0.01";
  if (part < total && percent === "100") percent = ">99.99";
  return { series, index, value, display: `${percent}% (${part}/${total})` };
}

function readChart(source: string): Chart | null {
  let input: unknown;
  try {
    input = JSON.parse(source);
  } catch {
    return null;
  }
  if (!isObject(input)) return null;
  const { title, mode, series, groups } = input;
  const unit = typeof input.unit === "string" ? input.unit.trim() : "";
  if (
    !isLabel(title) ||
    (mode !== "grouped" && mode !== "stacked") ||
    !isLabel(unit) ||
    !Array.isArray(series) ||
    !series.length ||
    !series.every(isLabel) ||
    !Array.isArray(groups) ||
    !groups.length
  )
    return null;
  const result: Group[] = [];
  let maximum = 0;
  for (const group of groups) {
    if (
      !isObject(group) ||
      !isLabel(group.label) ||
      !Array.isArray(group.values) ||
      group.values.length !== series.length
    )
      return null;
    const values: Datum[] = [];
    let total = 0;
    for (const [i, raw] of group.values.entries()) {
      const item = datum(raw, series[i], i, unit, mode);
      if (!item) return null;
      values.push(item);
      if (mode === "stacked") total += item.value;
      else maximum = Math.max(maximum, item.value);
    }
    if (!Number.isFinite(total)) return null;
    if (mode === "stacked") {
      // Remove floating-point addition noise from fractional numeric inputs.
      if (!Number.isInteger(total)) total = Number(total.toPrecision(15));
      if (unit === "%" && total > 100) return null;
      maximum = Math.max(maximum, total);
    }
    result.push({ label: group.label, values, total });
  }
  return {
    title,
    mode,
    unit,
    groups: result,
    maximum: unit === "%" ? 100 : maximum,
  };
}

function BarTrack({ values, maximum }: { values: Datum[]; maximum: number }) {
  return (
    <HStack className="article-chart-track" aria-hidden="true" gap={0}>
      {values.map((item) => (
        <HStack
          as="span"
          key={item.index}
          className="article-chart-segment"
          data-ink={String(item.index % 5)}
          style={{
            inlineSize: `${maximum > 0 ? (item.value / maximum) * 100 : 0}%`,
          }}
        />
      ))}
    </HStack>
  );
}

export function ArticleChart({
  source,
  fallback,
}: {
  source: string;
  fallback: ReactNode;
}) {
  const id = useId();
  const chart = useMemo(() => readChart(source), [source]);
  if (!chart) return fallback;
  const stacked = chart.mode === "stacked";
  return (
    <figure
      className="article-chart"
      data-mode={chart.mode}
      aria-labelledby={id}
    >
      <figcaption id={id}>
        <Text weight="semibold">{chart.title}</Text>
      </figcaption>
      {chart.groups.map((group, index) => (
        <VStack
          key={index}
          className="article-chart-group"
          gap={2}
          role="group"
          aria-label={group.label}
        >
          <HStack className="article-chart-heading" gap={2}>
            <Text weight="semibold">{group.label}</Text>
            {stacked && (
              <Text type="supporting" color="secondary">
                합계 {group.total}
                {chart.unit}
              </Text>
            )}
          </HStack>
          {stacked && (
            <BarTrack values={group.values} maximum={chart.maximum} />
          )}
          <ul className="article-chart-values" role="list">
            {group.values.map((item) => (
              <li key={item.index}>
                <HStack className="article-chart-label" gap={2} vAlign="center">
                  <HStack
                    as="span"
                    aria-hidden="true"
                    className="article-chart-key"
                    data-ink={String(item.index % 5)}
                  />
                  <Text type="supporting">{item.series}</Text>
                  <Text
                    type="supporting"
                    weight="semibold"
                    className="article-chart-value"
                  >
                    {item.display}
                  </Text>
                </HStack>
                {!stacked && (
                  <BarTrack values={[item]} maximum={chart.maximum} />
                )}
              </li>
            ))}
          </ul>
        </VStack>
      ))}
      <HStack className="article-chart-scale" aria-hidden="true">
        <Text type="supporting" color="secondary">
          0{chart.unit}
        </Text>
        {chart.maximum > 0 && (
          <Text type="supporting" color="secondary">
            {chart.maximum}
            {chart.unit}
          </Text>
        )}
      </HStack>
    </figure>
  );
}
