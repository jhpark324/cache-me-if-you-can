# 아키텍처 인덱스

지원 목표는 Windows·macOS·Linux의 로컬 네이티브 실행이며 WSL은 선택 사항이다. Codex와 자체 웹을 진입점으로 사용한다. 로컬 MCP는 지식 CRUD를 제공하며, 웹 질문의 지식 조회·모델 호출·답변 생성 흐름은 FastAPI 서버 내부의 LangGraph로 처리한다. 모델은 자체 웹의 ChatGPT OAuth 로그인으로 연결한다.

제품 범위는 [제품 개요](../project/product-brief.md)에서 확인한다. 아래 문서는 현재 구조·기술 계약과 제안을 구분한다. KURE-v2의 WSL 기술 실험은 [별도 보고서](../research/kure-v2-feasibility/report.md)에 기록했으며 제품 구현·전체 OS 지원 완료와 구분한다.

| 문서 | 읽는 조건 |
| --- | --- |
| [현재 구현 구조](current-system.md) | 시스템 경계·모듈·ER·배포 구성을 코드와 함께 확인할 때 |
| [다이어그램 모음](diagrams/index.md) · [브라우저에서 전체 보기](overview.html) | 도식으로 구현·흐름·제안의 차이를 살펴볼 때 |
| [백엔드·웹 구성 경계](component-boundaries.md) | 공통 도메인 서비스와 화면 모듈의 책임을 확인할 때 |
| [저장·검색·출처 실행 흐름](runtime-flows.md) | 저장·분류·답변·수정·삭제·OAuth의 시퀀스와 상태를 볼 때 |
| [유지보수 점검](maintenance-review.md) | 현재 책임 경계와 후속 리팩토링의 근거·완료 기준을 확인할 때 |
| [에이전트용 지식 계층](knowledge-layer.md) | 저장 단위, 관계, 검색·답변 근거와 변경·삭제를 설계할 때 |
| [데이터 스키마](data-schema.md) | SQLite 기록·버전·주제·관계, Lance 청크와 작업 상태의 필드·타입·제약을 구체화할 때 |
| [MCP·웹 서비스 계약](service-contracts.md) | 공통 입출력 타입, CRUD·검색·그래프 DTO, 삭제 확인·충돌·오류를 정할 때 |
| [저장 후 주제 연결·Markdown 청크](ingestion-and-chunking.md) | 서버의 concept_hints 해석·후속 연결·실패 처리와 헤더/블록/문장 분할·겹침·원문 위치를 구현할 때 |
| [저장 본문 작성 원칙·MCP 맥락 제안](record-body-format.md) | 자유형 본문의 현재 규칙, 스킬의 유형별 작성 골격과 별도 검색 응답 보완안을 검토할 때 |
| [검색·에이전트 맥락 계약](retrieval-and-context.md) | 청크와 Node 연결, 조건 변경·상충, 맥락 반환과 답변의 근거 검증을 구현할 때 |
| [스키마 서비스 적합성 검토](schema-fit-review.md) | 현재 구조를 유지할 근거와 상세 조회·출처 정정·맥락 적용·Node 검색의 검증 경계를 확인할 때 |
| [기술 스택 선정](technology-stack.md) | 확정한 AI 실행 구조와 저장소·검색·프론트엔드·패키징 추천을 확인할 때 |
| [로컬 검색과 임베딩](search-and-embedding.md) | LanceDB·SQLite 역할, CPU 임베딩 모델 선정, 한국어 검색과 색인 정합성을 설계할 때 |
| [운영체제 지원 설계](platform-support.md) | Windows·macOS·Linux 네이티브 실행, CPU 아키텍처별 의존성과 배포·검증 범위를 정할 때 |
| [ADR-001: LangGraph 기반 AI 실행](../decisions/ADR-001-langgraph-agent-runtime.md) | LangGraph 채택 이유, 대안과 실행·저장 경계를 확인할 때 |
| [ADR-002: 로컬 검색과 임베딩](../decisions/ADR-002-local-search-and-embedding.md) | LanceDB 도입과 CPU 기본 모델의 채택 근거를 확인할 때 |
| [ADR-003: KURE-v2 임베딩](../decisions/ADR-003-kure-v2-embedding.md) | 한국어 MVP의 모델 변경, 다중 벡터 계약과 조건부 채택 범위를 확인할 때 |
| [ADR-004: 그래프 시각화 라이브러리](../decisions/ADR-004-graph-visualization-library.md) | 3d-force-graph 조합의 채택 이유와 렌더링·도메인 경계를 확인할 때 |
| [ADR-005: MCP Python SDK v2](../decisions/ADR-005-mcp-python-sdk-v2.md) | 공식 SDK v2·날짜 프로토콜 버전·Streamable HTTP와 실제 클라이언트 검증 범위를 확인할 때 |
| [ADR-006: 휴지통·복원 없는 soft delete](../decisions/ADR-006-soft-delete-without-trash.md) | 삭제 표시의 내부 보존과 제품의 조회·수정 차단을 확인할 때 |

기능 동작과 수용 기준은 [기능 명세](../specs/index.md)에 작성한다. 대안과 선택 이유를 장기적으로 보존해야 하는 결정은 [결정 기록](../decisions/index.md)에 남기고 관련 설계에서 링크한다.
