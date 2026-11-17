# MCP·웹 서비스 계약

- 상태: 현재 공통 서비스 계약. 검증 절차는 [검증 안내](../guides/testing.md) 참조
- 작성일: 2026-11-02
- 용어: [도메인 용어](../project/domain-language.md)
- 기준: [데이터 스키마](data-schema.md), [지식 계층](knowledge-layer.md), [검색과 맥락 선택](retrieval-and-context.md), [MCP v2 채택](../decisions/ADR-005-mcp-python-sdk-v2.md)

MCP와 웹 API는 같은 도메인 서비스·Pydantic 요청/응답 모델을 사용한다. 별도 구현마다 삭제·버전·공개 범위 규칙을 다르게 만들지 않는다. 생성된 OpenAPI와 MCP 입출력 스키마는 서버 구현이 기준이며, 자동·실제 연결 확인 절차는 검증 안내에서 관리한다.

## MCP 실행 기준

- 공식 Python SDK **v2**, 초기 통합 검증 후보 `mcp==2.3.0`; SDK가 요구하는 `mcp-types` 버전을 함께 잠근다.
- 현재 프로토콜 규격은 **`2026-07-28`**이다. SDK의 `2.x`, JSON-RPC의 `2.0`, 아래 제품 DTO의 `schema_version=1`은 각각 다른 버전이다.
- `from mcp.server import MCPServer`와 Streamable HTTP를 사용한다. MCP endpoint는 `/mcp`, 웹 API는 `/api/v1`을 기준으로 분리한다.
- `streamable_http_app()`로 만든 ASGI 앱을 FastAPI에 통합하고 최상위 lifespan에서 `mcp.session_manager.run()`을 실행한다. 경로가 `/mcp/mcp`가 되거나 하위 lifespan이 누락되지 않게 한다.
- SDK는 현재 규격과 이전 클라이언트 규격을 지원한다. 실제 Codex 연결에서 사용한 규격과 도구·사용자 확인 기능을 검증한다. SDK v2 설치만으로 Codex의 기능 지원을 보장하지 않는다.
- 삭제 확인을 위해 HTTP 응답은 SSE를 사용한다. Codex 0.164.0 폼 호환을 위해 선택적인 루트 스키마 title은 제거하며 필수 확인 값은 유지한다. [호환성 근거와 검증](../specs/cache-me.md)을 따른다.

프로토콜 세부 메시지·호환 처리는 SDK에 맡긴다. 현재 규격의 stateless 요청 구조를 저장소 트랜잭션이나 단일 검색의 실행 중 메모리 상태가 없어야 한다는 뜻으로 해석하지 않는다. [공식 v2 안내](https://py.sdk.modelcontextprotocol.io/whats-new/), [ASGI 통합](https://py.sdk.modelcontextprotocol.io/run/asgi/), [규격 호환](https://py.sdk.modelcontextprotocol.io/protocol-versions/)

## 공통 타입

문서와 화면의 기록·기록 버전·세부 항목·주제·출처 참조는 각각 `Capture`·`CaptureRevision`·`Node`·`Concept`·`SourceRef`에 대응한다. 아래 타입·필드·도구 이름은 호환 식별자로 유지한다.

| 타입 | 필드·의미 |
| --- | --- |
| `SourceRef` | `capture_id: UUID`, `revision_id: UUID`, `node_id: UUID?`, `body_start/end: int?`. span은 둘 다 생략하거나 함께 지정하고 revision/Node의 범위를 벗어나지 않아야 함. 서버의 참조·조회 자격 검증과 에이전트의 의미상 근거 판단을 구분 |
| `ExpectedVersion` | `expected_revision_id: UUID`, `expected_state_version: int`. 본문뿐 아니라 공개 범위·삭제 변경과의 충돌도 감지 |
| `IndexState` | `status: pending \| ready \| failed \| excluded`, `profile_id`, `build_id`, `index_generation`, `error_code?`. 저장 성공과 별개 |
| `CaptureView` | `id`, `revision_id`, `revision_no`, `is_current`, `state_version`, `title?`, `body_markdown`, `kinds[]`, `visibility`, `completion_state?`, `event_time?`, `deleted_at`, `created_at`, `updated_at`, `revision_created_at`, `index_state`, `node_status`, `nodes: NodeView[]`, `concept_hints[]`, `concept_state: ConceptState`, `concepts: ConceptView[]`, `sources: SourceView[]`, `review_state`, `review_reason?` |
| `CaptureSummary` | 식별자·버전·제목/본문 일부·유형·시각·검색 상태·review_state. 전체 본문·Node·출처 목록은 포함하지 않음 |
| `MutationResult` | `capture: CaptureView?`, `committed_ref: SourceRef?`, `request_id`, `replayed: bool`, `result_state: available \| unavailable`, `warnings[]`. 커밋 결과를 가리킴 |
| `SearchHit` | `source: SourceRef`, `excerpt`, `matched_spans[]`, `matched_node_ids[]`, `score`, `score_kind: maxsim \| bm25 \| rrf`, `index_profile_id`, `index_generation`. 원본 검증 후 생성; 점수는 청크 검색 값 |
| `Page[T]` | `items: T[]`, `next_cursor: string?`. cursor는 정렬/필터에 묶인 불투명 값 |
| `DomainError` | `code`, `message`, `retryable`, `details?`. 원문·비밀정보·스택 추적을 넣지 않음 |
| `DeleteResult` | `request_id`, `capture_id`, `revision_id`, `state_version`, `deleted_at`, `index_state.status=excluded`, `replayed`. 최초 삭제 커밋 영수증이며 본문은 포함하지 않음 |
| `ConceptView` | `id`, `name`, `description?`, `aliases[]`, `state_version`, `created_at`, `updated_at` |
| `ConceptState` | `status: pending \| running \| ready \| failed`, `job_id?`, `requested_revision_id?`, `applied_revision_id?`, `unresolved_hints[]`, `error_code?`. 본문 저장·색인 상태와 별개. `unresolved_hints`는 호환성을 위해 빈 배열로 반환하며, 이전 작업의 `needs_review`는 `ready`로 조회. 의미는 [주제 연결 계약](ingestion-and-chunking.md)에 정의 |
| `NodeInput` | `kind`, `body_start/end`, `label?`, `origin`, `verification_state`, `verification_note?`, `concept_hints[]`(기본 `[]`). Node의 주제 ID·ordinal·Node ID는 서버가 결정 |
| `NodeView` | `id`, `revision_id`, `ordinal`, NodeInput의 의미 필드, `text`, `concepts: ConceptView[]`, 부모 `source: SourceRef`, 부모 `review_state`. text는 저장본 span에서 읽음 |
| `SourceView` | `source: SourceRef`(저장 당시 참조), `resolved_source: SourceRef?`(조회 가능한 현재 또는 안전하게 동등한 참조), `availability: available \| unavailable`, `review_state: valid \| needs_review`, `reason?` |

성공 응답은 `{schema_version: 1, ok: true, data: ...}`, 실패 응답은 `{schema_version: 1, ok: false, error: DomainError}` 형태를 기준으로 한다. `data/error` 동시 사용을 허용하지 않는다. 앱 필드는 snake_case이며 MCP wire의 `inputSchema`, `outputSchema`, `structuredContent` 같은 표준 필드 이름을 제품 규칙에 맞춰 바꾸지 않는다.

`MCPServer`의 타입 모델에서 입력·출력 JSON Schema를 생성하고 실제 요청·응답을 검증한다. 저수준 도구 스키마 광고만으로 서버가 입력을 검증했다고 가정하지 않는다. MCP 결과는 `structuredContent`에 구조화 객체를 담고 필요한 텍스트 표현도 같은 객체에서 생성한다. 별도의 LLM 재요약을 저장 결과처럼 표시하지 않는다. [도구 스키마](https://py.sdk.modelcontextprotocol.io/servers/tools/), [구조화 출력](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)

## 입력 제한과 상세 조회

| 항목 | 초기 구현 기준 |
| --- | --- |
| 기록 본문 | 최대 100,000 Unicode code points 및 UTF-8 1 MiB를 모두 만족. 공백만 있는 값 거부 |
| 질문 요청 | 검색 질문 원문 최대 10,000 code points 및 UTF-8 64 KiB. 질문을 조용히 자르지 않음 |
| 페이지 | 기본 20, 최대 100. limit은 1 이상; 초과 입력은 오류 |
| Node | revision마다 최대 200개. 초과하면 오류이며 일부를 버리지 않음 |
| 주제 힌트 | 기록/Node의 각 `concept_hints` 필드당 최대 20개. 각 값은 공백만 있는 값 금지·최대 100 code points |
| 삭제 확인 | 발급 후 5분. 대상·버전·호출자에 결합한 일회용 토큰 |
| 임베딩 검색 질의 | 모델 마커·특수 토큰 포함 64토큰. 초과는 QUERY_TOO_LONG |

제한값은 실행 시험 전 시작값이며 글자 수를 토큰 수로 환산한 값이 아니다. 시각·문자열 위치·ID는 데이터 스키마를 따른다. 알 수 없는 입력 필드는 거부한다.

`node_status`는 `absent | current | stale`이며 Node가 현재 본문과 맞는지를 나타낸다. 사실 검증 여부가 아니다. NodeInput의 enum·기본값은 데이터 스키마를 따른다. 기록과 Node의 주제는 별도이며 기록의 모든 주제를 모든 Node에 자동 부여하지 않는다.

SourceRef 검증은 존재·같은 brain·소속·span·현재 조회 자격을 확인한다. 이것만으로 내용이 주장을 지지하거나 객관적으로 참이라고 증명되지는 않는다. `review_state=valid`는 현재 출처 의존성을 사용할 수 있다는 뜻이며 `verification_state=verified`와 별개다. SourceView.reason은 `source_changed | source_deleted | upstream_invalid`다. 삭제·접근 불가 출처는 기존 참조와 상태만 반환하며 본문·제목을 재노출하지 않는다.

삭제되지 않은 기록은 관리 상세에서 `needs_review`인 본문도 읽어 정정할 수 있다. 이를 현재 답변의 유효한 근거로 사용하지 않는다. `capture_get(revision_id=...)`는 명시적 이력 조회이며 `is_current=false`를 표시한다. 부모가 삭제되면 현재·과거 revision과 Node 모두 NOT_FOUND다. `node_get`은 현재 revision의 Node만 직접 조회하고 과거 Node는 명시적 Capture 이력 상세에서만 읽는다. 동등성 해석은 SourceView의 저장 참조와 resolved_source로 구분하며 오래된 node_get을 조용히 다른 Node로 바꾸지 않는다.

## 생성·수정 요청

### `CreateCaptureInput`

| 필드 | 필수·기본값 | 의미 |
| --- | --- | --- |
| `request_id: UUID` | 필수, 웹/Skill 어댑터가 생성 | 재시도 때 동일 값을 재사용; 사용자가 직접 입력할 필드는 아님 |
| `body_markdown: string` | 필수, 공백만 있는 값 거부 | 저장할 전체 정리본 |
| `title: string?` | null | 제목 없이 저장 허용 |
| `kinds: RecordKind[]` | `[]` | [기록 유형 설계안](../project/record-types.md)의 여섯 값. 과거 procedure/reflection/plan은 각각 knowledge/episode/idea로 해석한다. 중복 없는 다중 유형 또는 미분류 허용; 별도 분류 승인을 필수로 만들지 않음 |
| `visibility: public \| private` | `public` | 생성 기본값. 실제 공유 활성화가 아님 |
| `completion_state` | null | `incomplete \| completed \| null` |
| `event_time: EventTime?` | null | 내용에 알려진 날짜 표현만 보존 |
| `nodes: NodeInput[]` | `[]` | 본문 span·의미·origin·verification 필드; 저장 전 검증 |
| `concept_hints: string[]` | `[]` | 선택적인 주제 이름·분류 힌트. 서버가 본문과 기존 주제를 비교해 실제 ID를 결정 |
| `sources: SourceRef[]` | `[]` | 기존 지식을 재사용한 정리본은 알려진 출처를 제출 |

최소 사용자 입력은 본문이다. `id`, `brain_id`, 현재 revision, 생성 시각, `deleted_at`, 색인 상태, 소유 권한은 서버가 결정한다. 생성 시 `deleted_at=null`이며 일반 수정으로 삭제 시각을 바꾸지 않는다. 전달하지 않은 필드와 명시적으로 전달한 null을 구분한다. 알 수 없는 필드는 거부한다.

생성·일반 수정·병합의 기본 계약은 기록과 Node의 `concept_ids`를 입력받지 않는다. 외부 LLM에 주제 ID 조회·생성을 요구하지 않으며, 서버 내부의 공통 LangGraph 작업이 저장 후 주제를 연결한다. 실제 연결은 `concepts`로 반환한다. 주제 ID는 읽기·검색 필터와 아래 명시적 연결 정정 명령에만 사용한다. 저장 후 처리·실패·경합과 서버 청크 생성은 [주제 연결·청크 계약](ingestion-and-chunking.md)을 따른다.

```json
{
  "request_id": "bc02598a-5141-44e0-a090-ec6e831ff93b",
  "body_markdown": "트랜잭션의 원자성은 변경을 전부 반영하거나 전부 취소하는 성질이다.",
  "concept_hints": ["데이터베이스", "트랜잭션"]
}
```

이 요청은 제목·유형·완료 상태를 강제하지 않고 `visibility=public`으로 저장한다. `concept_hints`를 생략해도 저장된다. 응답에는 실제 커밋한 본문과 revision, `index_state.status=pending` 등의 검색 준비 상태, 별도의 `concept_state.status=pending`을 반환한다. 주제 연결 실패가 이미 성공한 본문 저장을 실패로 바꾸지 않는다.

### `UpdateCaptureInput`

- `request_id`, `capture_id`, `expected_revision_id`, `expected_state_version`, `changes`가 필수다.
- `changes`에는 제목·본문·유형·공개 범위·완료 상태·사건 시각·Node·주제 힌트·출처 중 실제 바꿀 필드만 넣는다.
- 일반 필드는 생략 시 유지, nullable 필드의 null은 값 제거, 유형·Node 배열 `[]`는 명시적 비우기다. `concept_hints: []`는 힌트만 비우며 연결 제거가 아니다. 실제 연결 정정은 `capture_set_concepts`를 사용한다. 수정에서 `visibility`를 생략하면 기존 값을 유지하며 public으로 되돌리지 않는다. Node의 본문 변경 예외와 출처 보호는 아래 규칙을 우선한다.
- 본문 변경 시 유효한 Node를 제출하면 `node_status=current`다. 기존 Node 구조가 있는데 새 Node를 생략하면 새 revision에는 Node를 비우고 `stale` 및 `NODES_STALE` 경고를 반환한다. 명시적인 `nodes: []`는 `absent`이며 기존 Node가 없던 기록은 본문만 바꿔도 absent다.
- 본문이 같고 Node를 생략하면 의미·span·Node 주제를 새 ID로 복제한다. 이전 stale은 메타데이터 변경만으로 current가 되지 않는다. 과거 Node·revision은 변경하지 않으며 기록·Node 주제만 바뀐 안전한 승계는 데이터 스키마의 동등성 규칙을 따른다.
- `sources`는 일반 배열 비우기 규칙을 적용하지 않는다. 기존 출처가 있으면 이를 유지하고 제출한 SourceRef를 중복 없이 추가한다. 생략이나 `sources: []`만으로 의존성을 지우거나 `needs_review`를 해제하지 않는다. 출처 교체·제거는 아래 `capture_review_sources` 계약으로 처리한다.
- 본문·완료 상태·유형·주제 힌트·출처 등 저장 내용이 바뀌면 새 revision을 만든다. 공개 범위만 바뀌면 Capture의 상태 버전·검색 세대를 바꾼다. 주제 연결 작업의 재등록 여부는 [주제 연결 계약](ingestion-and-chunking.md)을 따른다.
- `change_kind`는 완료 상태만 바꾸면 `completion_change`, 그 외 내용·메타데이터 변경이나 혼합 변경은 `edit`다. 병합 전용 명령은 `merge`다.
- 기대 버전이 다르면 자동 덮어쓰기·자동 병합 없이 `VERSION_CONFLICT`를 반환한다.

### `MergeCapturesInput`

- `request_id`, `target_capture_id`, 대상의 `ExpectedVersion`, `sources: SourceRef[]`, `merged_body_markdown`이 필수다.
- 사용자가 지정한 대상에 새 revision을 만든다. 소스가 요청 시점과 같고 접근 가능한지 확인하며 출처를 연결한다.
- 나머지 원본 기록은 변경하지 않는다. 유사도만으로 이 명령을 실행하지 않는다. 선택적 nodes/concept_hints/kinds를 받으며 생략한 일반 메타데이터는 대상 값을 유지한다. 본문이 바뀌므로 Node 처리에는 Update와 같은 재제출·stale 규칙을 적용한다.
- 기존 대상의 알려진 출처와 새 병합 출처를 보존한다. 대상의 이전 revision은 자체 이력으로 남기며 자기 Capture를 provenance 출처로 넣지 않는다. 자기 참조·순환은 거부한다.

## 출처 재검토 — `capture_review_sources`

`ReviewSourcesInput`은 `request_id`, `capture_id`, `ExpectedVersion`, **`replacement_sources: SourceRef[]` 전체 목록**, 공백이 아닌 `review_reason`이 필수다. 선택적으로 `body_markdown`, `nodes`를 받는다. 명시적인 정정·재검토 요청에 따른 쓰기이며 매번 새 승인 화면을 추가하지 않는다.

1. 삭제되지 않은 대상과 기대 버전을 읽고 기존 출처 전체와 비교한다. 새 출처의 형식·소속·span·삭제 여부·현재 또는 안전하게 동등한 revision·상위 의존성을 확인한다. 제출한 출처나 상위 의존성이 무효하면 요청 전체를 거부하고 기존 revision과 재검토 상태를 유지한다.
2. 남길 출처와 교체·제거 이유, 어떤 주장과 구간을 다시 확인했는지를 기록한다. A1→A2 교체를 기존 출처와 합집합하지 않는다.
3. 알려진 의존성을 완전히 제거하려면 그 의존 내용을 제거하거나 독립적인 내용으로 **본문을 다시 작성**하고 이유를 명시해야 한다. 같은 본문에 replacement_sources 빈 배열만 제출하는 요청은 거부한다. 새 독립 근거가 있으면 출처를 제출하고, 외부 자료·새 사용자 진술은 본문에 출처와 한계를 남긴다. 자동 사실 인증으로 취급하지 않는다.
4. 같은 Capture의 갱신된 출처가 기존 주장을 여전히 지지하면 본문을 유지한 교체를 허용한다. 의미상 적합성은 저장 에이전트가 실제 구간을 읽고 검토해야 한다. 서버의 참조 검증·본문 변경 여부만으로 진실성이나 독립성을 완전히 증명했다고 표시하지 않는다.
5. 대상 자신이나 대상에 의존하는 기록을 새 출처로 넣어 순환시키지 않는다. 쓰기 트랜잭션에서 대상·출처·검사한 의존 경로의 버전/상태를 재검사하고 달라지면 VERSION_CONFLICT, 순환이면 SOURCE_CYCLE이다. LLM 검토 중 DB 쓰기 트랜잭션을 열지 않는다.
6. 성공하면 `change_kind=source_review`, `review_reason`을 가진 새 revision과 **새 전체 출처 집합**을 만들고 상태·검색 세대·outbox·receipt를 함께 커밋한다. 옛 revision·출처는 보존한다. 본문 변경 시 Node 처리는 Update와 같다.

review_state는 서버가 전체 현재 출처로 계산하며 클라이언트가 valid를 직접 설정하지 않는다. 재검토 뒤 출처가 다시 바뀌면 다시 needs_review가 된다. 원문 대화나 읽지 않은 외부 링크를 내부 SourceRef처럼 만들지 않는다.

## 주제와 관계

`concept_create`는 `request_id`, `name`, 선택적 `description/aliases`를 받아 서버 ID와 `state_version=1`인 ConceptView를 반환한다. `concept_list`는 선택적 문자열 `query`, `limit/cursor`로 이름·별칭을 찾고 `concept_get`은 ID로 조회한다. 동명 후보는 구분해 반환하며 자동 병합·전역 이름 UNIQUE를 적용하지 않는다. 목록은 관리·저장용이며 그래프에는 조회 가능한 기록/Node에 연결된 주제만 표시한다.

`concept_update`는 `request_id`, `concept_id`, `expected_state_version`, `changes{name?, description?, aliases?}`를 받는다. 이름은 비울 수 없고 description null·aliases 빈 배열은 제거다. 성공하면 상태 버전이 증가한다. 이름 변경으로 기록 내용·주체·범위를 바꾸지 않는다. 개별 주제의 물리 삭제·병합 관리 기능은 넣지 않는다.

`relation_type`은 [일곱 관계 유형](../project/domain-language.md#관계-유형과-표시-이름)을 사용한다. 웹 선택지·표시와 MCP·API가 같은 값을 사용하며 표시 이름을 별도 enum으로 취급하지 않는다.

`RelationInput`은 `request_id`, `relation_type`, `source: SourceRef`, `target: SourceRef`, `evidence: SourceRef`, 선택적 `scope_note/evidence_note`다. 같은 brain의 조회 가능한 현재 또는 안전하게 동등한 참조를 사용하고 커밋까지 상태를 다시 검사한다. 구조 검증은 관계 의미의 진실성을 보장하지 않는다.

- `relation_create`는 검증한 관계를 추가한다. `RelationView`는 `id`, 위 참조·종류·설명, `created_at`, `withdrawn_at?`, `withdrawal_reason?`다. 단순 유사도에서 인과를 만들지 않는다.
- `relation_list`는 `capture_id` 또는 `node_id`, 선택적 종류, `direction: incoming | outgoing | both`(기본 both), `limit/cursor`를 받는다. 기본 조회는 철회·삭제된 끝점/근거·유효하지 않은 참조를 제외한다. 관계 이력은 삭제되지 않은 기록의 명시적 revision 이력에서만 제공한다.
- `supersedes`는 **새 조건 → 이전 조건**이다. source/target 각각 Node 또는 정확한 span, 근거 span, 필수 scope_note/evidence_note로 주체·상황·시점과 명시적인 변경을 표시한다. 범위 불명확은 INVALID_RELATION_SCOPE이며 일반 관련 관계로 저장할 수 있다. 대체 관계의 순환은 거부한다. 혼합 기록 전체를 자동 무효화하지 않는다.
- `relation_retract`는 `request_id`, `relation_id`, 공백이 아닌 `withdrawal_reason`으로 명시적 관계 정정을 처리한다. 원관계·기록을 보존하고 withdrawn_at/withdrawal_reason을 한 번만 설정한다. 최초 성공 재시도는 같은 결과를 반환하며 다른 이유로 덮어쓰지 않는다. 별도 관계 복구 동작은 없다. 기록 삭제가 아니므로 삭제 확인 토큰을 요구하지 않는다.

일반 기록/Node 저장은 힌트를 받아 서버가 주제를 연결하며 Node 독립 편집 도구를 두지 않는다. 본문만 저장해도 정상 동작하며 주제·Node 생성은 필수 선행 호출이 아니다. `concept_create/list/get/update`는 명시적인 주제 관리와 내부 서비스의 후보 조회 기능이며 일반 저장자가 먼저 호출해야 하는 단계가 아니다.

명시적 주제 정정의 `SetConceptsInput`은 `request_id`, `capture_id`, `ExpectedVersion`, `concept_ids: UUID[]`가 필수이고 `node_concepts: [{node_id, concept_ids[]}]`는 선택적이다. 기록 주제의 전체 목록을 교체하며 Node 목록은 생략하면 유지, 제출하면 전체 교체한다. 같은 brain·현재 Node 소속·존재·중복을 검증한다. 성공은 `MutationResult`이며 새 `edit` revision과 `concept_state.status=ready`를 반환한다. 상세한 빈 목록·경합·후속 재분류 의미는 [주제 연결 계약](ingestion-and-chunking.md)을 따른다. 이 관리 명령은 본문·Node 의미를 편집하지 않는다.

관계 승계·철회와 supersedes 적용은 [검색과 맥락 선택](retrieval-and-context.md)을 따른다.

실패한 자동 주제 작업의 명시적 재시도는 MCP `capture_retry_concepts`와 `POST /api/v1/captures/{id}/concept-retry`로 제공한다. `RetryConceptsInput`은 `request_id`, `capture_id`, `ExpectedVersion`, `job_id`를 받으며 현재 failed 작업만 pending으로 전환한다. 본문/revision/state_version은 유지하고 `MutationResult`를 반환한다. 같은 요청은 영수증으로 재생하며 `JOB_NOT_RETRYABLE`은 HTTP 409다. [운영 후속 계약](../specs/runtime.md)에 lease·경합·취소·로그인 시도 취소 API의 상세를 둔다.

## 도구와 웹 경로

| 동작 | MCP 도구 | 웹 API | 결과 |
| --- | --- | --- | --- |
| 기록 추가 | `capture_create` | `POST /api/v1/captures` | MutationResult |
| 목록 | `capture_list` | `GET /api/v1/captures` | Page[CaptureSummary] |
| 상세·명시적 이력 | `capture_get` | `GET /api/v1/captures/{id}` + revision_id 선택 | CaptureView |
| 수정 | `capture_update` | `PATCH /api/v1/captures/{id}` | MutationResult |
| 병합 | `capture_merge` | `POST /api/v1/captures/{id}/merge` | MutationResult |
| 명시적 주제 연결 정정 | `capture_set_concepts` | `PUT /api/v1/captures/{id}/concepts` | MutationResult |
| 실패 주제 작업 재시도 | `capture_retry_concepts` | `POST /api/v1/captures/{id}/concept-retry` | MutationResult |
| 출처 재검토 | `capture_review_sources` | `POST /api/v1/captures/{id}/source-review` | MutationResult |
| 삭제 확인 준비 | `capture_delete_prepare` | `POST /api/v1/captures/{id}/deletion-preview` | DeletionPreview |
| 확인 후 삭제 | `capture_delete` | `POST /api/v1/captures/{id}/deletion` | DeleteResult |
| 출처 패널 조회 | `source_get` | `POST /api/v1/sources/resolve` | SourceDetail |
| Node 구간 조회 | `node_get` | `GET /api/v1/nodes/{id}` | NodeView |
| 주제 생성·목록·상세·수정 | `concept_create/list/get/update` | `POST/GET /api/v1/concepts`, `GET/PATCH /api/v1/concepts/{id}` | ConceptView 또는 Page |
| 관계 추가·조회 | `relation_create/list` | `POST/GET /api/v1/relations` | RelationView 또는 Page |
| 관계 철회 | `relation_retract` | `POST /api/v1/relations/{id}/retraction` | RelationView |
| 지식 검색 | `knowledge_search` | `POST /api/v1/search` | Page[SearchHit] |
| 홈 지식 개요 | 웹 전용 | `GET /api/v1/graph` | GraphView |
| 주변 지식 | `knowledge_neighbors` | `GET /api/v1/captures/{id}/neighbors` | GraphView |
| 질문에 쓸 맥락 | `knowledge_context` | `POST /api/v1/context` | ContextResult |
| 웹 질의응답 | 기본 MCP는 조회 도구 제공 | `POST /api/v1/questions` | 이벤트 스트림·AnswerResult |

일반 조회는 deleted_at IS NULL인 기록만 대상으로 한다. 삭제된 기록의 목록·상세·이력·Node 조회, 상태 필터 우회, 수정·병합·출처 재검토는 제공하지 않는다. 삭제된 기록을 반환하게 하는 입력 필드는 허용하지 않는다. 모든 관련 도구에서 부모 기록 상태를 확인한다.

## 삭제 확인 계약

삭제는 deleted_at을 null에서 서버 시각으로 한 번 설정하는 soft delete다. 물리 데이터·revision·출처는 보존하지만 사용자 기능에서 접근할 수 없다. 되돌리기·삭제 목록·수동/자동 영구 삭제는 제공하지 않는다.

DeletionPreview는 `confirmation_token`, `capture_id`, `expected_revision_id`, `expected_state_version`, 현재 제목/미리보기, `expires_at`를 포함한다. 서버에는 token hash·brain/호출자·참조·만료/사용 시각을 남기고 발급 후 5분 동안 해당 대상·버전의 삭제에만 사용한다.

1. 대상을 표시하고 삭제 후 서비스에서 조회·수정할 수 없음을 알린 뒤 사용자에게 다시 확인받는다. 웹은 명시적 확인 동작, MCP는 지원되는 Resolve/Elicit 등 사용자 응답 경로를 사용한다.
2. 실행 요청의 request_id·토큰은 재시도에서 재사용한다. 호출 권한과 같은 성공 receipt를 먼저 확인하고 성공한 요청을 다시 실행하지 않는다.
3. 새 실행은 deleted_at IS NULL·기대 revision/상태 버전·토큰의 대상/호출자/기간/미사용을 확인한다. 변경·만료·취소·확인 미지원이면 변경하지 않는다.
4. SQLite 트랜잭션에서 삭제 시각·상태 버전·검색 세대·검색 제외 상태·토큰 사용·receipt·remove outbox를 함께 커밋한다. 이 동기 커밋이 삭제 완료다. 파일 정리를 기다리지 않고 모든 읽기 경로에서 즉시 제외한다.
5. 같은 성공 요청에는 최초 DeleteResult를 replayed=true로 반환하며 본문을 재생하지 않는다. 다른 요청으로 같은 대상을 다시 삭제하려 하면 일반 NOT_FOUND다.

**토큰 소지나 모델이 보낸 confirmed=true만으로 사람의 확인이 증명되지는 않는다.** 확인 응답은 모델이 임의 생성하는 도구 인수와 분리한다. destructiveHint는 힌트이며 확인을 강제하지 않는다. SDK 왕복 요청 상태와 앱 삭제 토큰도 별개다. [사용자 입력 의존성](https://py.sdk.modelcontextprotocol.io/handlers/dependencies/), [왕복 요청](https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/)

Codex의 실제 확인 지원과 Skill 재질문 응답의 연결은 연동 시험이 필요하다. 미지원일 때 확인 없이 실행하는 fallback은 없고 Skill·웹 양쪽의 재확인 요구를 유지한다.

## 검색·답변·그래프 계약

`SearchInput`은 검색 질의, 유형·주제·사건 시각 등의 선택적 조건, limit/cursor를 받는다. 소유 범위는 서버 맥락에서 정하며 본인 검색에는 private 기록도 포함한다. 벡터와 FTS에 같은 조건을 적용한다.

명시적인 유형 필터가 없으면 미분류를 포함한 모든 관련 기록을 검색 대상으로 둔다. 에이전트가 추정한 RecordKind는 탐색 힌트이며 그것만으로 다른 유형을 모두 배제하지 않는다. 검색된 context·decision을 후속 맥락으로 쓸 때에는 대상·시점·출처·상충 내용을 함께 읽는다. 유형 자체가 현재 유효성이나 실행 권한을 보장하지 않는다. ContextItem/ContextResult와 여러 기록의 변경·충돌 처리는 [검색과 맥락 선택](retrieval-and-context.md)에 정의한다.

임베딩에 넣는 질의가 64토큰 예산을 넘으면 조용히 자르지 않는다. MCP의 검색 도구는 토큰 길이·처리 가능한 예산을 담은 `QUERY_TOO_LONG`을 반환해 에이전트가 의미별로 나누게 하는 것을 초기 계약으로 한다. 웹의 `QuestionInput`은 원 질문을 유지하고 LangGraph가 필요할 때 짧은 검색 질의로 분해한다. 웹 질문은 위 문자/바이트 제한을 적용하며 임베딩의 64토큰 한계와 구분한다.

검색 결과는 현재 SQLite 저장본으로 검증하고 snippet을 만든다. 여러 청크가 같은 기록을 찾으면 중복을 묶되 관련 span을 유지한다. 무효 후보를 제외한 뒤 예산 안에서 추가 조회하며 근거가 없으면 빈 결과를 반환한다.

`AnswerResult`는 `answer_id`, `limitations[]`, `parts: AnswerPart[]`, `evidence_status: found | insufficient | none`, `sources: SourceRef[]`를 기준으로 한다. `AnswerPart`는 요청 안에서 고유한 `part_id`, `kind: stored_knowledge | general_explanation`, `text`, `sources[]`를 갖는다. 저장 사실에 대한 부분은 유효한 근거를 요구한다. 일반 설명을 사용자 경험으로 표현하지 않고, 답변을 자동으로 지식에 저장하지 않는다. 스트림·취소·재검증 순서는 [검색과 맥락 선택](retrieval-and-context.md#답변과-스트리밍)의 구현 기준을 따른다.

`GraphView`는 `nodes[]`, `edges[]`, `truncated: bool`을 갖는다. 홈 개요와 선택 기록의 1홉 탐색 모두 최대 50개 노드/100개 관계로 제한하고 상한으로 잘렸음을 표시한다. 노드는 `kind: capture | concept | node`, 안정적인 도메인 ID, 표시 이름, 필요한 SourceRef로 구성한다. Capture 노드에는 표시용 기록 유형 `kinds[]`도 반환한다. 관계는 끝점 ID·종류·방향·근거 참조를 갖는다. 표시할 수 없는 기록의 이름·연결을 우회 노출하지 않는다. 3D 좌표·색상·패널 위치는 지식 스키마의 필수 필드로 만들지 않고 별도 화면 설계에서 다룬다.

홈의 `GET /api/v1/graph`는 반복 쿼리 매개변수 `kinds`, `concept_ids`를 받는다. 최근 현재 기록을 시작점으로 SQLite의 실제 주제 연결·Node·명시적 관계를 반환하며 임베딩 준비 상태와 독립적으로 동작한다. 후보·출처 검증에도 예산을 적용하고 생략이 있으면 `truncated=true`로 알린다. 필터를 벗어난 기록을 관계 확장으로 되살리지 않는다. 페이지 커서나 전체 개수는 반환하지 않으며 필터·검색·선택 기록 주변 탐색으로 범위를 좁힌다. 상세 동작과 화면 수용 기준은 [홈 그래프 개선](../specs/workspace.md)을 따른다.

홈 그래프의 `capture` 노드에는 현재 기록 버전의 `concept_state: {status, error_code}`를 포함한다. `status`는 상세 조회와 같은 `pending | running | ready | failed`이며 공급자 원문이나 작업 비밀은 포함하지 않는다. 표시된 기록의 상태를 한 번의 배치 조회로 읽고 과거 버전의 실패를 현재 상태로 표시하지 않는다. 이 메타데이터는 화면 갱신·복구 안내용이며 간선을 대신하지 않는다. 선택 기록의 주변 그래프도 현재 세부 항목의 `NodeConcept` 주제 연결을 `has_topic` 간선으로 반환하며 해당 세부 항목의 SourceRef를 근거로 사용한다.

`ContextInput`은 검색용 query·동일 필터, 선택적 subject_hint/situation_hint/as_of, limit(기본 10, 최대 10개 기록)을 받는다. 힌트는 검증된 사실이나 권한이 아니다. knowledge_context도 64토큰을 넘는 query를 거부한다.

`QuestionInput`은 `request_id`, `question`, 선택적 `kinds/concept_ids/event_time` 검색 조건이다. 각 요청은 독립된 단일 검색·응답이며 이전 요청의 대화·응답 이력을 입력으로 받지 않는다. 요청 안에서 LangGraph가 추가 검색할 수 있지만 요청 사이의 대화 상태는 만들지 않는다.

웹은 현재 입력·응답·출처 선택 상태만 화면에 보유한다. 새 검색은 별도 request_id를 생성하고 이전 요청을 취소할 수 있다. 늦게 도착한 이전 request_id의 이벤트는 현재 결과 화면에 적용하지 않는다. 서버도 요청 종료·취소 후 실행 맥락을 해제하며 검색 원문·답변을 DB·로그 본문·영구 체크포인트에 자동 저장하지 않는다.

출처 클릭은 `source_get(SourceRef)` / `POST /api/v1/sources/resolve`로 정확한 revision·Node·span을 다시 검증해 `SourceDetail`을 반환하고 오른쪽 슬라이드 패널에 표시한다. SourceDetail은 `source`, `is_current`, `current_revision_id?`, `text`, 부모 `capture: CaptureView`, 해당 `node: NodeView?`, `review_state`를 갖는다. 이 경로는 사용자 클릭에 따른 명시적 저장본 조회이며 과거 revision이면 그 사실을 표시하고 현재 본문으로 바꿔치기하지 않는다. 부모가 삭제되거나 조회 자격이 없어졌으면 NOT_FOUND와 내용 없음으로 처리한다. 현재 답변 근거로 재사용하려면 별도로 현재성·출처 유효성을 검사한다.

### 이번 질문에서 읽은 청크

`completed.result.retrieval`은 `{items: [{source: SourceRef, label, capture_label, cited}], truncated: bool}`이다. 서버가 실제 읽고 자격을 검증한 최대 20개 근거 구간을 반환한다. 같은 기록의 서로 다른 구간은 구별하고 선택 필드의 누락과 null은 같은 참조로 취급한다. 표시 문자열은 기존 PII 정제 후 각각 최대 60 Unicode code point로 줄이며, `cited`는 최종 검토를 통과한 답변 출처로 결정한다. 모델이 만든 인용 여부나 검색 후보 목록을 그대로 전달하지 않는다.

최종 전송 전 미인용 근거도 현재 revision·삭제·검토 상태·버전을 다시 확인한다. 무효 미인용 근거는 제외하고 `truncated=true`로 표시한다. 인용된 근거가 바뀌면 기존 답변 실패/무효화 처리를 유지한다. 본문 범위는 검색 시 맥락 확장으로 원래 임베딩 청크보다 넓을 수 있다.

웹은 완료된 답변에 묶인 임시 청크 노드와 부모 연결을 기존 홈 그래프에 겹쳐 표시한다. 정본 그래프의 50노드/100간선에 최대 20개 청크·10개 부모 기록·20개 연결만 추가한다. 데이터베이스에 Node나 Relation을 저장하지 않으며 새 질문·닫기·실패·취소·필터/기록 변경 시 제거한다. 이전 응답에 이 필드가 없으면 홈 그래프만 유지한다. [화면·정확한 구간 선택 수용 기준](../specs/workspace.md)

## 오류와 재시도

| code | 의미·처리 |
| --- | --- |
| `VALIDATION_ERROR / INPUT_TOO_LARGE` | 잘못된 타입·enum·빈 본문·유효하지 않은 span·크기 제한 초과 |
| `NOT_FOUND` | 조회할 수 있는 대상이 없음; 삭제된 내용이나 다른 소유자의 존재를 상세 노출하지 않음 |
| `VERSION_CONFLICT` | 기대 revision/state_version과 현재가 다름; 다시 조회하고 수정 범위 재확인 |
| `IDEMPOTENCY_CONFLICT` | 같은 request_id에 다른 요청 내용 |
| `INVALID_SOURCE_REF / SOURCE_CYCLE` | 잘못된 출처·소속·순환 의존성 |
| `SOURCE_REVIEW_REQUIRED` | 출처 교체·의존성 제거의 본문/이유/근거 재검토 필요 |
| `INVALID_RELATION_SCOPE / RELATION_ALREADY_WITHDRAWN` | 대체 범위 불명확 또는 이미 철회된 관계의 다른 철회 요청 |
| `CONFIRMATION_REQUIRED/EXPIRED/UNSUPPORTED` | 삭제 확인 단계 필요·만료·클라이언트 확인 수단 미지원; 변경 없음 |
| `QUERY_TOO_LONG` | 검색 질의 토큰 예산 초과; 원 질문 의미를 유지해 분해 |
| `INDEX_NOT_READY / CURSOR_STALE` | 색인 미준비 또는 페이지 기준 변경. 낡은 본문으로 대신하지 않음 |
| `RESULT_UNAVAILABLE` | 이미 커밋한 작업의 결과가 현재 삭제 상태나 조회 자격 때문에 표시 불가; 해당 작업을 다시 실행하거나 기록을 다시 생성하지 않음 |

도메인 오류는 웹 HTTP 상태와 MCP의 도구 오류 표현으로 일관되게 매핑한다. MCP에서는 실패 DTO의 `ok:false`와 함께 도구 결과의 `isError:true`를 설정해 정상 성공으로 오해되지 않게 한다. JSON-RPC 자체의 malformed request·알 수 없는 method 오류와 구분한다. 성공 receipt를 재사용할 때에도 현재 공개 범위·삭제 상태를 확인하고 삭제된 본문을 재생하지 않는다.

모든 쓰기의 request_id는 서버가 정한 호출자 범위와 결합하고 operation·정규화된 payload fingerprint가 같아야 한다. Concept/Relation 응답에도 request_id/replayed를 함께 반환한다. 성공 receipt는 과거 쓰기의 중복 방지 근거이며 현재 조회 자격은 매번 확인한다.

목록 cursor는 필터·정렬·마지막 키에, 검색 cursor는 질의·필터·프로필/build에 결합한다. 다음 페이지도 SQLite 상태를 재검사하며 기준을 유지할 수 없으면 CURSOR_STALE를 반환한다. 장시간 snapshot을 연 채 모델을 실행하지 않는다.

## 후속 검증

Pydantic에서 JSON Schema/OpenAPI를 생성할 때 기본값·필수 여부·null·PATCH 생략 의미와 예시를 자동 검증한다. Codex의 SDK/규격 호환, 생성 응답의 실제 커밋 내용, 업데이트 충돌, 삭제 사용자 확인, 상세 Node/주제/출처 왕복, 출처 정정 후 QA 복귀, Node stale, scoped supersedes·철회, 소프트 삭제 후 이력/Node 제외와 중복 재시도, 낡은 검색 후보 차단을 통합 검증한다. 설치·클라이언트 왕복·모델 호출은 아직 이 문서 작업에서 수행하지 않았다.
