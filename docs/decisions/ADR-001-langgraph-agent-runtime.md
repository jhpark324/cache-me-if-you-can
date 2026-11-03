# ADR-001: FastAPI 내부 AI 실행에 LangGraph 채택

- 상태: `accepted`
- 작성일: 2026-11-02
- 관련 기능·설계: [제품 기획](../project/product-brief.md), [기술 스택 선정](../architecture/technology-stack.md), [지식 계층](../architecture/knowledge-layer.md)
- 후속 범위 변경: 아래 당시의 휴지통 표현은 현재 [ADR-006](ADR-006-soft-delete-without-trash.md)의 soft delete·조회 차단으로 대체됐다. 휴지통·복원 기능은 제공하지 않는다.

## 배경

자체 웹에서 질문하면 FastAPI 서버가 로컬 지식을 조회하고 자체 ChatGPT OAuth로 모델을 호출해 답변한다. 검색 결과에 따라 상세 조회·관계 확장·추가 검색을 선택하고, 저장본 참조와 현재 버전·휴지통 상태를 확인해야 한다. 외부 Codex의 MCP 도구와 서버의 답변 생성은 같은 지식 서비스를 사용한다.

LangGraph와 Pi를 비교한 뒤 사용자가 LangGraph로 진행하기로 명시적으로 결정했다. 이는 실행 프레임워크의 채택이며, 구현이나 실제 OAuth·검색 품질 검증이 완료됐다는 뜻은 아니다.

## 검토한 대안

| 대안 | 장점 | 단점 |
| --- | --- | --- |
| LangGraph | Python/FastAPI 안에서 상태·분기·반복 조회를 명시적으로 관리할 수 있다. | 그래프 상태와 전이를 설계하고 의존성 호환성을 관리해야 한다. |
| 공식 SDK와 작은 도구 루프 | 고정된 짧은 흐름을 적은 구성으로 구현할 수 있다. | 추가 조회·재시도·종료 조건의 상태 관리를 직접 작성해야 한다. |
| Pi | 모델·OAuth 연동과 에이전트 도구 루프를 재사용할 수 있다. | TypeScript SDK를 Python 서버와 연결하는 추가 런타임과 통신 설계가 필요하다. |

Pi는 `badlogic/pi-mono`로 알려졌던 현재의 `earendil-works/pi`를 뜻한다. 대안 비교는 OAuth 지원 유무가 아니라 현재 서버 언어와 실행 제어 범위를 기준으로 한다. [LangGraph 공식 문서](https://docs.langchain.com/oss/python/langgraph/overview), [Pi 공식 저장소](https://github.com/earendil-works/pi)

## 결정

AI 실행에 LangGraph를 채택하고 FastAPI 프로세스 안에서 Python `StateGraph`를 실행하는 구조로 설계한다. 질문 해석·검색·필요한 기록 조회·답변 생성·근거 확인을 구성하며, 부족한 맥락의 추가 조회에는 호출·시간·조회량 예산을 둔다.

모델 호출은 자체 OAuth 어댑터와 OpenAI Async SDK로 연결하는 방향으로 설계한다. LangChain 모델 래퍼는 필수로 두지 않는다. 공급자 로그인·토큰 갱신·요청 제약은 모델 어댑터가 처리한다. [임의 LLM과 스트리밍](https://docs.langchain.com/oss/python/langgraph/streaming#use-with-any-llm)

LangGraph가 관리하는 실행 상태와 장기 지식을 분리한다. 기록·버전·주제·관계·휴지통과 검색 색인은 공통 지식 서비스가 관리한다. 내부 조회 노드는 이 서비스를 직접 호출하며 질의응답에는 읽기 도구만 제공한다. 추가·수정·삭제는 기존의 명시적 CRUD 계약을 따른다.

체크포인터는 선택 사항이며 초기 요청 상태는 메모리에서 관리하는 방향으로 설계한다. 영구 대화 저장이나 중단 후 재개의 필요성은 별도 명세에서 결정한다. 별도 Agent Server와 LangSmith도 현재의 필수 구성으로 두지 않는다. [상태 영속화](https://docs.langchain.com/oss/python/langgraph/persistence)

## 결과와 후속 조치

- 분기와 상태를 명시적으로 표현하는 대신 그래프 설계·관찰·검증 비용을 감수한다. 검색 품질은 별도의 평가로 판단한다.
- 질의응답 기능 명세에서 노드의 입력·출력, 조회 예산, 답변과 출처의 스트리밍 시점, 오류·취소 계약을 정의한다.
- [현재 운영체제 지원 목표](../architecture/platform-support.md)에 따라 Windows·macOS·Linux에서 자체 OAuth 로그인, 모델 스트리밍, 지식 도구 호출, 갱신·취소 및 예산 초과 종료를 검증한 뒤 호환 버전을 고정한다.
- 기록 수정·휴지통 이동 후 실행 상태의 오래된 참조를 재검증하고 후속 답변에 재사용하지 않는지 확인한다. 체크포인트를 도입할 경우 재개 경로에도 같은 조건을 적용한다.
- SQLite·검색·임베딩·프론트엔드 등 나머지 기술의 추천 상태는 이 결정으로 바뀌지 않는다. 구현·실측 결과는 기능 검증 문서에 기록한다.

## 대체 관계

- 대체하는 결정: 없음. 기술 스택 문서의 직접 도구 루프 추천을 갱신한다.
- 이 결정을 대체한 기록: 없음.
