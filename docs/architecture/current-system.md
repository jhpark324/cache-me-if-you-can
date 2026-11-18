# 현재 구현 구조

이 문서는 현재 실행 구조를 설명한다. 선택 이유는 [ADR](../decisions/index.md), API 제약은 [서비스 계약](service-contracts.md), 질문 처리 계약은 [실행 명세](../specs/runtime.md), 재현 가능한 검증은 [검증 안내](../guides/testing.md)를 따른다. 전체 운영체제 지원 완료를 의미하지 않는다.

## 시스템과 신뢰 경계

```mermaid
flowchart TB
    User[사용자] --> Web[React 웹]
    User --> Codex[Codex + 기록 스킬]
    subgraph Local[사용자 기기]
      Web -->|세션 + CSRF| API[FastAPI /api/v1]
      Codex -->|로컬 bearer| MCP[MCP /mcp/]
      API --> Domain[공유 기록·검색 서비스]
      MCP --> Domain
      Domain --> SQL[(SQLite 정본)]
      Domain --> Lance[(LanceDB 파생 색인)]
      Worker[색인 worker] --> Embed[KURE-v2 CPU]
      SQL --> Worker
      Embed --> Lance
      API --> Graph[create_agent ReAct 질문 처리]
      Graph -->|검색·근거 재조회 도구| Domain
      Classifier[LangGraph 주제 분류] --> Domain
      SQL --> TopicLinks[주제 정의 변경 보강]
      TopicLinks -->|본문 검색·연결 추가| Domain
      Graph --> PII[PIIMiddleware 입력·출력 정제]
      Classifier --> PII
      TopicLinks --> PII
      PII --> Auth[서버 OAuth 모델 어댑터]
    end
    Auth -->|OAuth·선택된 질문/본문 맥락| Provider[외부 ChatGPT 모델 서비스]
    Embed -. 최초 모델 다운로드 .-> HF[Hugging Face]
```

기록과 검색 색인은 로컬에 저장하지만 답변·저장 후 주제 분류·주제 정의 변경 보강은 외부 모델 호출이다. 따라서 **완전한 오프라인 AI 제품으로 표현하지 않는다**. 자체 로그인은 모델 계정 연결이며 로컬 웹 사용자 간 접근 제어·다중 사용자 인증과 다르다. `visibility=public`은 미래 공유를 위한 메타데이터이고 현재 인터넷 공개를 실행하지 않는다. `private`도 현재 모델 전송 금지를 뜻하지 않는다. 공유/전송 정책은 별도 후속 설계다.

모델 경계에서는 내장 `PIIMiddleware`의 이메일·신용카드·IP 탐지 결과를 `redact`로 대체한다. 질문·도구 결과·도구 인수·응답의 전송용 사본에 적용하며 SQLite 정본·revision·SourceRef 위치·출처 패널은 유지한다. 이것은 저장 허용 여부의 판정이나 모든 개인정보의 익명화를 뜻하지 않는다. 이름·전화번호·의미 기반 민감성 판정과 기존 저장 자료의 소급 정제는 포함하지 않는다.

## 실행 모듈

```mermaid
flowchart TB
    App[App.tsx 화면 조합] --> UI[편집·연결·설정·그래프 컴포넌트]
    App --> Client[api.ts 요청과 SSE]
    Client --> Main[main.py 구성·lifespan·HTTP 보호]
    Main --> HTTP[api.py 기록 라우터]
    Main --> MCP[mcp_server.py 어댑터]
    HTTP --> Records[records.py 도메인 트랜잭션]
    MCP --> Records
    MCP --> Search[search.py 검색·맥락·그래프]
    Main --> Search
    Main --> Questions[questions.py 요청·답변 검증]
    Questions --> Agent[question_agent.py create_agent·호출 예산]
    Agent --> Tools[question_tools.py 읽기 도구·근거 장부]
    Tools --> Search
    Tools --> Records
    Agent --> Chat[chat_model.py OAuthChatModel]
    Chat --> Auth[auth.py OAuth·모델 호출]
    Questions --> Auth
    Auth --> PII[privacy.py PIIMiddleware 정제]
    Main --> Enrich[enrichment.py 주제 분류]
    Enrich --> Auth
    Enrich --> Records
    Main --> Backfill[topic_backfill.py 연결 보강]
    Backfill --> Auth
    Backfill --> Search
    Backfill --> BackfillJobs[topic_backfill_jobs.py 영속 작업·판단]
    BackfillJobs --> Records
    Search --> Records
    Records --> Filters[record_filters.py 공통 필터]
    Search --> Filters
    Records --> DB[db.py / models.py]
    Search --> Chunk[chunking.py / embedding.py]
    Search --> DB
```

| 경계 | 실제 코드 | 책임·변경 시 함께 확인할 항목 |
| --- | --- | --- |
| 조립·수명 | [main.py](../../backend/src/cache_me/main.py) | 서버 lock, 작업 취소, 세션/CSRF·Origin·Host, 정적 웹, 백업 |
| 로컬 실행·연결 | [runtime.py](../../backend/src/cache_me/runtime.py), [codex_integration.py](../../backend/src/cache_me/codex_integration.py) | 명시적 백그라운드 시작·동일 서버 재사용, 읽기 전용 진단, Codex 설정·스킬·비밀 없는 실행 정보 설치 |
| 계약 | [schemas.py](../../backend/src/cache_me/schemas.py), [outputs.py](../../backend/src/cache_me/outputs.py) | 웹/MCP 입력·출력. 프런트 [types.ts](../../frontend/src/types.ts)는 수동 동기화이므로 계약 변경 시험 필요 |
| 정본 변경 | [records.py](../../backend/src/cache_me/records.py) | 요청 멱등성, expected revision/state, 저장·삭제·주제·관계와 출처 검증 |
| 공통 선택 | [record_filters.py](../../backend/src/cache_me/record_filters.py) | 여러 유형은 OR, 여러 주제는 OR, 두 그룹은 AND. 현재 Node의 주제도 부모 기록 선택에 반영 |
| 파생 색인 | [search.py](../../backend/src/cache_me/search.py), [embedding.py](../../backend/src/cache_me/embedding.py) | 색인 세대, 모델 프로필, 검색 후 SQLite 재검증. 현재 제품은 정확 벡터 검색이며 ANN 실험과 구분 |
| 질문 실행 | [questions.py](../../backend/src/cache_me/questions.py), [question_agent.py](../../backend/src/cache_me/question_agent.py), [question_tools.py](../../backend/src/cache_me/question_tools.py) | ReAct 읽기 도구 총 8회, 에이전트 모델 9회와 별도 검토 1회, 요청 90초. 근거 ID·버전·필터는 서버 소유 |
| 모델 연결·PII | [chat_model.py](../../backend/src/cache_me/chat_model.py), [auth.py](../../backend/src/cache_me/auth.py), [privacy.py](../../backend/src/cache_me/privacy.py) | OAuth, 메시지·function call 왕복, 완료 후 응답 반환, 내장 PII 탐지. 인증 비밀은 그래프 상태에 넣지 않음 |
| 자동 분류 | [enrichment.py](../../backend/src/cache_me/enrichment.py) | LangGraph 분류·커밋 흐름. 본문 저장·로그인·임베딩과 독립 실패 가능 |
| 주제 연결 보강 | [topic_backfill.py](../../backend/src/cache_me/topic_backfill.py), [topic_backfill_jobs.py](../../backend/src/cache_me/topic_backfill_jobs.py) | 새 주제·실제 정의 변경의 본문 후보 조회, 제한된 모델 판단, 영속 lease·호출 예산·판단 캐시와 추가 전용 커밋 |
| 데이터 수명 | [db.py](../../backend/src/cache_me/db.py), [baseline 0001](../../backend/alembic/versions/0001_canonical_records.py), [주제 보강 0002](../../backend/alembic/versions/0002_topic_backfill.py), [아티클 0003](../../backend/alembic/versions/0003_article_metadata.py) | 짧은 `BEGIN IMMEDIATE`, WAL, 외래키, immutable trigger, 복원 금지 |
| 웹 상호작용 | [App.tsx](../../frontend/src/App.tsx), [RecordEditor.tsx](../../frontend/src/RecordEditor.tsx), [RecordBrowser.tsx](../../frontend/src/RecordBrowser.tsx), [RecordConnections.tsx](../../frontend/src/RecordConnections.tsx) | 기록 라이브러리·타임라인, 단일턴 검색, 필터, 출처 drawer, 명시적 CRUD. 저장 여부와 로딩·실패 표시 |

한 로컬 서버 프로세스에서 동작한다. 분산 큐·별도 벡터 서버·그래프 DB·LangSmith·영구 대화 체크포인터는 필수가 아니다. 두 DB의 작업을 하나의 원자적 트랜잭션으로 간주하지 않는다.

주제 정의 변경 보강은 새 주제나 실제 이름·설명·별칭 변경만 영속 작업으로 모아 처리한다. 기존 본문 검색으로 제한된 후보를 읽고 기존 연결을 보존하며 확정한 기록 연결만 추가한다. 수동 주제 정정 이력이 없는 일반 분류 `ready` 기록만 대상으로 하며 `pending/running`은 대기, `failed`는 제외한다. 일부 후보를 보류한 완료 및 이전 `needs_review`는 공개 상태 `ready`로 취급하며 사용자 검토 없이 자동 보강할 수 있다. 검색·색인 미준비나 부분 처리는 내부 상태로 남기고 저장 후 분류의 `concept_state`와 구분한다. 별도의 진행·제안 화면은 제공하지 않는다. 후보·모델 호출 예산과 적용 직전 검증은 [주제 연결 계약](ingestion-and-chunking.md#주제-정의-변경과-기존-기록-연결-보강)을 따른다.

기본 포트는 `52761`이며 `CACHE_ME_PORT`로 변경한다. `manage.py run`은 포그라운드 실행, `start`는 준비 완료를 확인하는 명시적 백그라운드 시작이다. `doctor`는 런타임과 설치 상태를 읽기 전용으로 진단한다. 설치된 스킬의 `runtime.json`이 같은 Python·데이터 경로·포트의 진단·시작 명령을 제공하며 인증 토큰은 담지 않는다. MCP 헤더 helper는 인증 정보 제공만 담당하고 도구 탐색 중에 서버를 시작하지 않는다. 서버의 정상 응답과 현재 Codex 대화의 도구 목록은 별도로 확인한다.

MCP 등록 키와 Python 패키지는 `cache_me`, 서버 표시 이름은 `Cache Me If You Can`, 스킬 이름과 실행 명령은 `cache-me`다. 설치기는 현재 이름의 설정만 관리하며 `install-codex --replace`로 해당 관리 설정·스킬을 갱신한다. 외부 작성 설정·잘못된 관리 구간은 보존하고 거부하며 다른 MCP 연결·스킬은 그대로 둔다. 이전 이름의 감지·자동 이전·별칭은 제공하지 않는다. 기본 데이터 디렉터리는 `CacheMe`이고 기록 스키마와 개별 MCP 도구의 의미는 유지한다. 설치·재연결 절차는 [로컬 실행 가이드](../guides/local-development.md#codex-mcp)를 따른다.

## 정본 데이터 관계

```mermaid
erDiagram
    LocalBrain ||--o{ Capture : owns
    Capture ||--|{ CaptureRevision : history
    CaptureRevision ||--o{ RevisionKind : purpose
    CaptureRevision ||--o{ KnowledgeNode : spans
    CaptureRevision ||--o{ RevisionConcept : topics
    Concept ||--o{ RevisionConcept : labels
    Concept ||--o{ ConceptAlias : aliases
    KnowledgeNode ||--o{ NodeConcept : topics
    Concept ||--o{ NodeConcept : labels
    CaptureRevision ||--o{ ProvenanceLink : derived_from
    CaptureRevision ||--o{ Relation : referenced_endpoint
    Capture ||--o{ IndexJob : outbox
    Capture ||--o{ ConceptEnrichmentJob : classification
    Concept ||--o{ TopicBackfillJob : definition_changes
    Concept ||--o{ TopicBackfillDecision : decisions
    Capture ||--o{ TopicBackfillDecision : classified_content
    Capture |o--o{ MutationReceipt : optional_target
    Capture ||--o{ DeletionConfirmation : confirmation
    EmbeddingProfile ||--o{ IndexBuild : builds
    IndexBuild ||--o{ CaptureIndexState : projection_state
```

ER 도식은 주요 연관을 압축했다. 정확한 FK·복합 키·제약은 [models.py](../../backend/src/cache_me/models.py)와 migration이 기준이다. 특히 `Relation`은 양 끝점과 근거, `ProvenanceLink`는 파생 revision과 원출처 revision/구간을 참조한다.

`Capture`는 삭제·공개 범위·현재 revision 포인터를 가진다. 본문은 immutable `CaptureRevision`에만 보관한다. Node는 본문의 Unicode code point 반개구간을 가리키며 별도 원문이 아니다. Concept는 자유 주제와 별칭, RecordKind는 정리본의 재사용 목적, 청크는 모델 토큰 상한에 맞춘 파생 검색 단위다. 네 가지를 한 태그 필드로 합치지 않는다.

## 배포 파일과 실행 데이터

```mermaid
flowchart LR
    Source[리모트 소스 + lockfiles] --> Setup[manage.py setup]
    Setup --> Venv[backend/.venv]
    Setup --> Build[frontend/dist]
    Venv --> Run[127.0.0.1 로컬 서버]
    Build --> Run
    Run --> Data[OS별 사용자 데이터 디렉터리]
    Data --> Canonical[cache-me.sqlite3 + WAL]
    Data --> Secrets[credentials.json / local-access.json]
    Data --> Index[LanceDB index]
    Canonical --> Backup[수동 SQLite snapshot ZIP]
    Backup -. 포함하지 않음 .-> Excluded[인증·모델·검색 색인]
    Source --> CI[CI 코드·계약·웹 시험]
```

현재 지원하는 설치 경로는 **소스 checkout + uv 환경 + 프런트 빌드**다. Python wheel에는 migration이 들어가지만 프런트 번들은 포함하지 않는다. wheel 하나를 완성된 데스크톱 제품처럼 배포해서는 안 된다. 실제 로그인·모델·네이티브 OS 검증은 CI의 모형 기반 검사와 별도다.

상태 전이와 시간 순서는 [실행 흐름](runtime-flows.md), 기술 부채와 우선순위는 [유지보수 점검](maintenance-review.md)을 참고한다.
