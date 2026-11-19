import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { createElement as h } from "react";
import { renderToStaticMarkup as html } from "react-dom/server";

const groups = {
  "기록과 원문": ["capture_create", "capture_list", "capture_get", "capture_update", "capture_merge", "source_get", "node_get"],
  "주제와 출처 정정": ["concept_create", "concept_list", "concept_get", "concept_update", "capture_set_concepts", "capture_retry_concepts", "capture_review_sources"],
  "기록 사이의 관계": ["relation_create", "relation_list", "relation_retract"],
  "검색과 연결 탐색": ["knowledge_search", "knowledge_context", "knowledge_neighbors"],
  "학습 아티클": ["article_create", "article_list", "article_get", "article_update"],
  "삭제 확인": ["capture_delete_prepare", "capture_delete"],
};

// The service enforces some cross-field rules that JSON Schema alone does not convey.
const pageLimit = "limit은 1~100입니다. cursor를 다시 쓸 때 목록의 기준이 달라지면 CURSOR_STALE이므로 첫 페이지부터 읽습니다.";
const guides = {
  capture_create: ["기록 저장", "커밋한 기록 본문, 기록 ID·버전, 출처 참조와 재처리 여부를 반환합니다.", "body_markdown은 공백을 제외한 내용이 있어야 합니다. 최대 100,000 코드 포인트와 UTF-8 1 MiB를 모두 만족해야 합니다. 색인과 주제 분류는 별도로 진행합니다."],
  capture_list: ["현재 기록 목록", "items에 기록 요약, next_cursor에 다음 페이지 위치를 담습니다.", pageLimit],
  capture_get: ["기록과 저장 버전 조회", "지정한 기록의 본문, 상태, 연결 주제·세부 항목·출처를 반환합니다.", "revision_id를 생략하면 현재본을 읽습니다. 삭제한 기록의 현재본과 과거본은 NOT_FOUND입니다."],
  capture_update: ["기록 수정", "명시한 변경을 반영한 기록과 커밋된 버전의 참조를 반환합니다.", "기대 기록·상태 버전이 달라졌으면 VERSION_CONFLICT입니다. changes에서 필드를 생략하는 것과 null을 보내는 것은 구분됩니다."],
  capture_merge: ["기록 병합", "완성된 병합 본문과 지정 출처를 대상 기록의 새 버전으로 저장합니다. 원본 기록은 각각 남습니다.", "현재 대상 버전과 하나 이상의 sources, 완성한 merged_body_markdown이 필요합니다. 자기·순환 출처는 SOURCE_CYCLE입니다."],
  source_get: ["지정 원문 구간 확인", "text에 그 버전의 선택 구간, capture에 같은 버전의 전체 기록을 담습니다. is_current로 현재 버전인지 알 수 있습니다.", "body_start와 body_end는 함께 보내거나 모두 생략합니다. 시작을 포함하고 끝을 제외하는 유니코드 코드 포인트 위치입니다. 지정한 세부 항목·원문의 경계를 벗어나면 INVALID_SOURCE_REF입니다."],
  node_get: ["세부 항목 조회", "세부 항목의 본문, 주제, 부모 기록과 버전을 가리키는 source를 반환합니다.", "현재 버전 소속 세부 항목만 직접 조회합니다. 과거 버전은 capture_get으로 확인합니다."],
  concept_create: ["주제 생성", "주제 ID, 이름·별칭·설명, 상태 버전과 처리 영수증을 반환합니다.", "같은 request_id에 다른 입력을 재사용하면 IDEMPOTENCY_CONFLICT입니다."],
  concept_list: ["주제 목록", "items에 주제 정의, next_cursor에 다음 페이지 위치를 담습니다.", pageLimit],
  concept_get: ["주제 정의 조회", "이름·설명·별칭·상태 버전을 가진 주제 하나를 반환합니다.", "대상을 찾을 수 없으면 NOT_FOUND입니다."],
  concept_update: ["주제 정의 수정", "수정된 주제 정의와 새 상태 버전을 반환합니다.", "expected_state_version이 달라졌다면 주제를 다시 읽습니다."],
  capture_set_concepts: ["기록·세부 항목의 주제 정정", "지정한 주제 연결을 반영한 기록을 반환합니다.", "대상 기록과 기대 버전, 확정할 concept_ids가 필요합니다. 세부 항목별 정정은 node_concepts에 담습니다."],
  capture_retry_concepts: ["주제 분류 재시도", "해당 기록의 현재 분류 상태를 포함한 처리 결과를 반환합니다.", "현재 실패한 job_id와 기대 버전이 필요합니다. 본문을 수정하는 작업과 분리됩니다."],
  capture_review_sources: ["기록 출처 재검토", "검토 이유와 바뀐 근거를 반영한 기록을 반환합니다.", "기존 출처 의존성을 제거할 때는 본문도 다시 작성해야 합니다. 이 조건을 만족하지 않으면 SOURCE_REVIEW_REQUIRED입니다."],
  relation_create: ["명시적 관계 생성", "관계 ID, 관계 유형과 출발·도착·근거 참조를 반환합니다.", "세 참조가 유효해야 합니다. 순환하는 대체 관계는 SOURCE_CYCLE입니다."],
  relation_list: ["관계 목록", "현재 유효한 관계 목록과 다음 페이지 위치를 반환합니다.", "capture_id 또는 node_id 중 하나 이상이 필요합니다. direction은 incoming, outgoing, both 중 하나입니다. " + pageLimit],
  relation_retract: ["관계 철회", "철회 시각과 사유를 포함한 관계와 요청 영수증을 반환합니다.", "대상 relation_id와 비어 있지 않은 withdrawal_reason이 필요합니다."],
  knowledge_search: ["의미·키워드 검색", "items와 next_cursor를 반환합니다. 각 결과에 source, title, excerpt, matched_spans, matched_node_ids, score, score_kind, index_profile_id, index_generation이 있습니다.", "limit은 1~100입니다. 검색 준비 전에는 INDEX_NOT_READY, 모델 질의 예산인 특수 토큰 포함 64토큰을 초과하면 QUERY_TOO_LONG입니다."],
  knowledge_context: ["근거와 상충 맥락 조회", "items, conflicts, relations, evidence_status, limitations, truncated를 반환합니다. 근거와 상충 관계, 예산 때문에 읽지 못한 범위를 함께 확인합니다.", "limit은 1~10입니다. 검색 준비와 질의 길이 검사를 거칩니다. 한 번의 응답은 기록 10개·구간 20개·20,000자 이내입니다."],
  knowledge_neighbors: ["기록 주변 그래프 조회", "nodes, edges와 상한에 걸렸는지 나타내는 truncated를 반환합니다.", "선택한 기록의 한 홉, 노드 50개·간선 100개 범위입니다. SQLite에 저장한 연결을 조회하므로 임베딩 모델 준비가 필요하지 않습니다."],
  article_create: ["아티클 발행", "article에 발행한 독립 아티클의 ID, 버전·본문·인용과 근거 상태를 담습니다.", "summary는 한 줄입니다. 본문에 사용하는 인용은 citations 배열의 1부터 시작하는 번호와 일치해야 합니다. 새 기록 출처는 읽고 검증할 수 있어야 합니다."],
  article_list: ["아티클 목록", "기록 목록과 분리된 아티클의 제목·요약·주제와 다음 페이지 위치를 반환합니다.", pageLimit],
  article_get: ["발행본과 인용 상태 조회", "지정한 아티클 버전의 본문·인용과 해당 기록 출처의 현재 열람 상태를 반환합니다.", "revision_id를 생략하면 현재 발행본을 읽습니다. 존재하지 않는 아티클·버전은 NOT_FOUND입니다."],
  article_update: ["아티클 개정 발행", "기존 아티클 ID 아래에 저장된 새 발행본과 요청 영수증을 반환합니다.", "기대 버전과 완성한 전체 제목·요약·본문·인용·주제 목록이 필요합니다. 버전 충돌은 VERSION_CONFLICT입니다."],
  capture_delete_prepare: ["삭제 미리보기", "제목·발췌, 대상·기대 버전, 만료 시각과 확인 토큰을 반환합니다.", "기대 버전이 일치해야 합니다. 미리보기는 기록을 유지하며 확인 토큰은 5분 동안 유효합니다."],
  capture_delete: ["사용자 확인 후 기록 삭제", "삭제한 기록·버전 ID, 삭제 시각·상태 버전·색인 제외 상태와 재처리 여부를 반환합니다.", "새 삭제에는 유효한 확인 토큰과 클라이언트가 수집한 사용자 승인이 필요합니다. 만료는 CONFIRMATION_EXPIRED입니다. 확인 값은 모델이 작성하는 arguments에 들어가지 않습니다."],
};

function typeText(schema) {
  if (schema.$ref) return schema.$ref.split("/").at(-1);
  if (schema.oneOf || schema.anyOf) return (schema.oneOf || schema.anyOf).map(typeText).join(" | ");
  if ("const" in schema) return JSON.stringify(schema.const);
  if (schema.enum) return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (schema.type === "array") return "array<" + typeText(schema.items || {}) + ">";
  return (schema.type || "JSON") + (schema.format ? " (" + schema.format + ")" : "");
}

function fields(schema, prefix = "") {
  const required = schema.required || [];
  const properties = schema.properties || {};
  const names = [...required, ...Object.keys(properties).filter((key) => !required.includes(key))];
  return h("dl", { className: "mcp-fields" }, names.map((name) => {
    const field = properties[name];
    const notes = ["minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"].filter((key) => key in field)
      .map((key) => key + " " + field[key]);
    if ("default" in field) notes.push("기본값 " + JSON.stringify(field.default));
    return h("div", { key: name }, h("dt", null, h("code", null, prefix + name), h("small", null, required.includes(name) ? "필수" : "선택")),
      h("dd", null, h("code", null, typeText(field)), notes.length > 0 && " · " + notes.join(" · ")));
  }));
}

function raw(label, data) {
  return h("details", { className: "mcp-json" }, h("summary", null, label),
    h("pre", null, h("code", null, JSON.stringify(data, null, 2))));
}

function expandSchema(entry, side, definitions) {
  const keys = entry[side + "Definitions"];
  if (!keys) return entry[side];
  return { ...entry[side], $defs: Object.fromEntries(keys.map((key) => [key, definitions[key]])) };
}

function tool(name, entry, definitions) {
  const [title, result, conditions] = guides[name];
  const input = expandSchema(entry, "input", definitions);
  const output = expandSchema(entry, "output", definitions);
  const top = Object.entries(input.properties);
  const wrapped = top.length === 1 && top[0][1].$ref ? top[0] : null;
  const primary = wrapped?.[1].$ref.split("/").at(-1);
  const others = Object.keys(input.$defs || {}).filter((key) => key !== primary);
  return h("details", { key: name, id: name, className: "mcp-tool" },
    h("summary", null, h("code", null, name), h("span", null, title)),
    h("div", { className: "mcp-body" },
      h("h4", null, "호출 인자"), fields(input),
      wrapped && h("h4", null, wrapped[0] + " 객체의 필드"),
      wrapped && fields(definitions[primary], wrapped[0] + "."),
      others.map((key) => h("details", { className: "mcp-terms", key },
        h("summary", null, h("code", null, key), " 필드"), fields(definitions[key]))),
      h("h4", null, "반환"), h("p", null, result), h("h4", null, "호출 조건"), h("p", null, conditions),
      raw("전체 입력 JSON Schema", input), raw("전체 출력 JSON Schema", output)));
}

const exampleNotes = {
  capture_create: "본문과 요청 ID를 보내면 data.capture.id와 data.capture.revision_id가 생깁니다.",
  source_get: "두 식별자와 첫 문장의 시작·끝을 보내면 data.text에 그 문장만, data.capture.body_markdown에는 전체 본문이 들어옵니다.",
  article_create: "같은 구간을 첫 번째 기록 인용으로 넣습니다. data.article.id는 새 글을 가리키며 본문의 [1]은 앞서 읽은 구간을 가리킵니다.",
};

export async function renderMcpGuide(document, inputFile) {
  const target = document.querySelector("[data-mcp-tools]");
  if (!target) return;
  const read = async (file) => JSON.parse(await readFile(join(dirname(inputFile), "contracts", file), "utf8"));
  const [{ definitions, tools }, examples] = await Promise.all([read("mcp-schemas.json"), read("mcp-examples.json")]);
  const described = Object.values(groups).flat();
  if (described.length !== new Set(described).size || [...described].sort().join() !== Object.keys(tools).sort().join()) {
    throw new Error("Each registered MCP tool must appear in exactly one guide group.");
  }
  target.innerHTML = Object.entries(groups).map(([label, names]) => html(h("section", { className: "mcp-group" },
    h("h3", null, label), names.map((name) => tool(name, tools[name], definitions))))).join("");
  document.querySelector("[data-mcp-examples]").innerHTML = examples.map(({ name, arguments: args, structuredContent }) =>
    html(h("article", { className: "mcp-example" }, h("h3", null, guides[name][0], " · ", h("code", null, name)),
      h("p", null, exampleNotes[name]),
      raw("tools/call에 보낸 params 전체", { name, arguments: args }),
      raw("응답의 structuredContent 전체", structuredContent)))).join("");
}
