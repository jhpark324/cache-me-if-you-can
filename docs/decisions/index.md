# 결정 기록 인덱스

공통 아키텍처나 중요한 제약에 대한 결정 이유를 ADR(Architecture Decision Record)로 관리한다.

| ID | 결정 | 상태 | 문서 |
| --- | --- | --- | --- |
| ADR-001 | FastAPI 내부 AI 실행에 LangGraph 채택 | `accepted` | [LangGraph 기반 AI 실행](ADR-001-langgraph-agent-runtime.md) |
| ADR-002 | LanceDB와 CPU 기반 로컬 임베딩 채택 | `accepted` | [로컬 검색과 임베딩](ADR-002-local-search-and-embedding.md) |
| ADR-003 | 한국어 MVP에 KURE-v2 다중 벡터 임베딩 조건부 채택 | `accepted` — 개발 기준 | [KURE-v2 임베딩](ADR-003-kure-v2-embedding.md) |
| ADR-004 | 3D 그래프 라이브러리 채택·기존 디자인 시안 폐기 | `accepted` | [그래프 시각화 라이브러리](ADR-004-graph-visualization-library.md) |
| ADR-005 | 공식 MCP Python SDK v2 채택 | `accepted` | [MCP Python SDK v2](ADR-005-mcp-python-sdk-v2.md) |
| ADR-006 | 휴지통·복원 없는 soft delete | `accepted` | [삭제 정책](ADR-006-soft-delete-without-trash.md) |

ADR-002의 저장소·CPU 결정은 유지하며 초기 모델·단일 벡터 계약은 ADR-003으로 대체했다.

삭제 범위는 2026-11-02 후속 사용자 요청에 따라 휴지통·복원 없이 soft delete만 제공하는 것으로 변경했다. 이전 ADR의 삭제·휴지통 관련 표현에는 [ADR-006](ADR-006-soft-delete-without-trash.md)과 [현재 제품 요구사항](../project/product-brief.md#변경과-삭제)을 우선한다.

- 파일명: `ADR-<세 자리 번호>-<kebab-case 이름>.md`
- 생성 시 [결정 템플릿](../templates/decision.md)을 사용한다.
- 상태: `proposed`, `accepted`, `superseded`.
- 단순한 구현 선택마다 ADR을 만들 필요는 없다. 여러 기능에 영향을 주거나 되돌리기 어려운 선택을 중심으로 기록한다.
- 기존 결정을 대체하면 이전 기록을 삭제하지 않고 새 ADR을 연결한다.
- 관련 작업을 할 때 필요한 결정만 읽는다.
