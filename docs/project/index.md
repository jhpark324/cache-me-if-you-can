# Cache Me If You Can

| 항목 | 내용 |
| --- | --- |
| 이름 | Cache Me If You Can |
| 현재 단계 | 로컬 제품 구현·검증, 홈 그래프와 시안의 차이 개선 |
| 개발 방식 | Spec-Driven Development |
| 문서 위치 | `docs/` |

## 제품 방향

Cache Me If You Can은 AI와 대화하며 정리한 지식, 경험, 일상과 감정, 메모를 로컬에 쌓고 그 지식을 바탕으로 질의응답하는 개인용 세컨드 브레인이다. 일정에 관한 메모는 기록할 수 있지만 일정 관리 기능은 현재 범위에서 제외한다.

프로젝트 이름은 2026-11-02 사용자 결정으로 확정했다. 기존 데이터·로그인·Codex 연결의 호환성을 위해 저장 디렉터리 `SecondBrain`, 코드 패키지 `second_brain`, MCP 키 `second_brain`과 환경 변수 접두사는 유지한다. 이는 표시 이름을 뜻하지 않는다.

지원 목표는 Windows·macOS·Linux에서 직접 실행하는 로컬 서버와 CPU 임베딩이다. WSL은 선택 사항이며, Codex와 자체 웹을 진입점으로 사용한다. 로컬 MCP로 데이터를 CRUD하고, 웹 질문의 검색·모델 호출·답변 생성 흐름은 FastAPI 서버 내부에서 처리한다. 모델은 자체 웹의 ChatGPT OAuth 로그인으로 연결한다. 원문이나 원본 대화 세션은 보관하지 않으며 저장 후 실제 저장 내용을 사용자에게 보여준다.

기본 저장은 새 기록 추가이며 명시적인 병합·수정 요청에만 기존 기록을 갱신한다. 답변에서는 저장 지식과 AI의 보충 설명을 구분한다. 삭제는 Skill과 웹에서 재확인 후 `deleted_at`을 설정하는 soft delete다. 본문·이력은 내부 보존하지만 삭제된 기록은 모든 제품 조회·검색·질의응답·수정에서 제외한다. 휴지통·삭제 기록 조회·복원·실행 취소·자동 삭제·보관 기한·수동 영구 삭제는 두지 않는다.

기록의 공개 범위는 `visibility` enum으로 관리하며 초기 값은 `public`, `private`, 기본값은 `public`이다. 실제 공유 활성화와 대상 설정은 별도로 다룬다.

## 문서

| 문서 | 읽는 조건 |
| --- | --- |
| [제품 발전 제안](evolution-proposals.md) | 주제 품질·검색 설명·데이터 교환·에이전트 컨텍스트의 도입 우선순위를 정할 때 |
| [제품 기획 초안](product-brief.md) | 대상 사용자, 사용 사례, 제품 범위와 우선순위를 논의할 때 |
| [기록과 공개 범위 설계안](record-and-visibility.md) | 저장 단위, 유형별 정보, 공개 범위의 기본값과 미래 공유를 설계할 때 |
| [기록 유형과 에이전트의 활용 맥락](record-types.md) | RecordKind의 의미·분류 경계와 에이전트가 개인 지식·선호·경험·계획을 해석하는 기준을 정할 때 |
| [MVP 범위와 사용 흐름](mvp-scope.md) | 첫 화면·검색 응답·출처 패널·주변 그래프·운영 범위와 첫 버전의 완료 조건을 확인할 때 |
| [검색 응답 참고 이미지](assets/search-answer-reference.png) | 사용자가 제시한 질문·단일 답변·출처 목록 구성을 확인할 때 |

## 설계와 기술 선정

지식 계층의 구체적인 설계는 에이전트에게 위임되었다. AI 실행은 FastAPI 내부의 LangGraph, 검색은 LanceDB로 확정했다. 임베딩은 CPU 기본·GPU 선택이며 KURE-v2 + MultiVectorEncoder를 한국어 MVP 개발 기준으로 조건부 채택했다. [지식 계층 설계](../architecture/knowledge-layer.md), [기술 스택 선정](../architecture/technology-stack.md), [로컬 검색과 임베딩](../architecture/search-and-embedding.md)을 기능 명세의 공통 기준으로 삼는다. SQLAlchemy·Alembic, React·TypeScript·Vite, uv·정적 웹 번들은 구현에 사용하며 실제 버전은 lockfile로 고정한다. WSL 검증과 전체 OS 지원은 구분한다.

제한된 홈 그래프·검색 기반 단일턴 응답·오른쪽 출처 패널·주변 그래프·수동 백업 생성은 [MVP 기획](mvp-scope.md)에 구체화했다. 채팅과 후속 대화 상태는 제공하지 않는다. 실제 로그인·갱신·Codex 삭제 확인·제한된 한국어 평가 결과는 [004 검증](../specs/004-local-runtime/validation.md)에 있으며 네이티브 OS와 사용자가 보류한 로그아웃 후 재로그인은 별도 관문이다. 초기 보고서의 제안 전체를 확정 요구사항으로 간주하지 않는다. 기능 간 순서는 [작업 계획](../plans/index.md)에서 관리한다.

MCP는 공식 Python SDK v2와 Streamable HTTP를 채택했다. SDK의 2.x와 프로토콜 규격 `2026-07-28`을 구분한다. 실제 Codex 연결과 삭제 확인의 호환성 보완은 004에서 검증했다. [MCP 채택 결정](../decisions/ADR-005-mcp-python-sdk-v2.md)

저장 구조와 입출력 계약을 구현 전에 구체화하기 위해 [데이터 스키마](../architecture/data-schema.md)와 [MCP·웹 서비스 계약](../architecture/service-contracts.md) 초안을 작성했다. 기록·버전·관계, 파생 출처, 검색 세대, 삭제 확인·멱등성·수정 충돌을 공통 기준으로 삼고 기능별 명세에서 실제 SQL·Pydantic 모델로 검증한다.

기본 저장은 주제 ID 대신 `concept_hints`를 받고, 서버 내부 에이전트가 본문 저장 뒤 주제를 찾아 연결한다. 실패해도 본문은 보존한다. 검색 청크는 Markdown 헤더·블록·문장 순서로 분할하며 512토큰 상한과 강제 분할 시 최대 64토큰 겹침을 초기 기준으로 둔다. [주제 연결·청크 계약](../architecture/ingestion-and-chunking.md)에 처리·경합·검증 조건을 정의하며 실제 결과는 004에서 관리한다.

그래프 시각화는 `3d-force-graph` + Three.js + `three-spritetext`로 확정했다. 폐기한 것은 001 초기 시안이며 003의 검정·유리·흰 글씨·주황 강조와 그래프 위 검색/답변·출처 구성을 실제 홈에 반영한다. [홈 그래프 개선](../specs/004-local-runtime/home-graph-refresh.md)과 [라이브러리 채택 결정](../decisions/ADR-004-graph-visualization-library.md)을 따른다.

KURE-v2의 [WSL CPU 기술 실험](../research/kure-v2-feasibility/report.md)을 완료하고 [모델 변경 결정](../decisions/ADR-003-kure-v2-embedding.md)을 기록했다. 작은 합성 평가·검색 구간 성능을 검증했으며 실제 사용자 기록·전체 앱·모든 OS 지원 완료와 구분한다. 세 운영체제 네이티브 실행 요구와 Intel Mac·Windows ARM 등 미해결 설치 조건은 [운영체제 지원 설계](../architecture/platform-support.md)에 기록한다.

일정 관리와 외부 전송 정책 설계는 현재 범위에서 제외한다. 다른 사람과의 공유는 장기 과제이며 상세 권한 모델은 현재 기술 선정의 선행 조건으로 두지 않는다.

문서 안의 설계안은 기능 명세와 구현 계약을 작성하면서 구체화한다. 기능별 수용 기준은 [기능 명세 인덱스](../specs/index.md)에서 관리한다.
