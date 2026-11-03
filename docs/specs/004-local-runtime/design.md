# 설계

`backend/src/second_brain`은 FastAPI 구성, 공통 RecordService, 별도 검색 worker, 인증, LangGraph, MCP 어댑터를 포함한다. `frontend`는 React·TypeScript·Vite로 실제 API를 호출한다. 빈 저장소에서 사용자가 선택하는 읽기 전용 예시는 별도 프런트 모드이며 저장·검색 근거로 사용하지 않는다. 빌드한 웹은 FastAPI에서 같은 origin으로 제공한다. 개발 프록시도 동일 API 경로를 사용한다.

홈은 실제 지식 그래프를 기본 작업 공간으로 두고 최근 기록·필터를 왼쪽, 검색과 단일 답변을 상단, 선택 출처를 오른쪽 패널에 배치한다. 그래프는 검색·출처 열기 중에도 유지한다. 조회 상한·현재 출처 검증·화면 검증은 [홈 그래프 개선](home-graph-refresh.md)을 따른다. 제품 표시 이름은 **Cache Me If You Can**이며 기존 데이터 경로와 통합 식별자는 호환성을 위해 유지한다.

데이터 경로는 platformdirs로 운영체제별 사용자 디렉터리를 선택하며 SECOND_BRAIN_DATA_DIR로 변경 가능하다. SQLite는 정본, LanceDB는 재생성 가능한 projection이다. 모델 준비는 명시적 작업으로 시작하고 준비 전에는 색인 상태를 표시한다.

OAuth는 공식 SIWC OSS dynamic registration을 사용한다. 안정적인 host ID와 계정별 issued client ID를 보관하며 OAuth callback URI는 127.0.0.1의 `/auth/callback`이다. 인증·갱신은 서버에서 수행하고 Responses 요청은 store=false/stream=true와 배열 input으로 실행한다. `OAuthChatModel`은 사용자·모델 메시지와 function call/output을 변환하며, 완료된 응답의 호출만 로컬 도구에 전달한다. SIWC에서 지원하지 않는 max_output_tokens는 보내지 않고, 텍스트·도구 인수 등을 포함한 수신 응답의 32,000자/UTF-8 128 KiB 상한 및 요청 시간 제한으로 실행을 제한한다. 실제 로그인 확인과 새 도구 왕복의 검증 결과는 구분한다.

MCP는 Python SDK 2.3.0의 MCPServer와 Streamable HTTP를 사용한다. 삭제 확인은 모델 입력에 없는 Resolve/Elicit 의존성으로 처리한다. 부모 ASGI lifespan이 MCP session manager를 실행한다.

검색/답변/출처 세부 동작은 [검색 계약](../../architecture/retrieval-and-context.md)을 따른다. SSE started/progress/answer_part/completed/invalidated/error 이벤트마다 request_id를 포함한다. 브라우저는 현재 요청 외 이벤트를 버리고 서버는 전송 직전 근거를 재검증한다.

웹 질문은 `/questions` 하나로 처리한다. `AnswerResponse`는 내부 근거 검증용 parts를 연속된 산문으로 표시하며 문단 끝에 작은 출처 번호를 붙인다. 별도 관련 기록 검색·목록과 반복 유형 제목을 제거한다. 출처 패널과 수동 저장의 SourceRef 연결을 유지하며, 상세 수용 기준은 [하나의 답변과 작은 출처](answer-reading.md)를 따른다.

## ReAct와 PII 후속 변경

`question_agent.py`의 `create_agent`가 읽기 전용 `search_knowledge`와 `read_evidence`를 선택한다. `question_tools.py`의 요청별 근거 장부는 현재 버전·원문 위치·고정 UI 필터·근거 수를 관리하고 모델이 보낸 근거 ID를 검증한다. `questions.py`는 원 질문 구간, 요청 수명, 답변 형식, 별도 근거 검토 및 최종 출처 검증을 담당한다. 기존 고정 `plan → gather → answer → check` 그래프는 이 흐름으로 대체했으며 자동 주제 분류의 LangGraph는 유지한다.

도구 호출은 배치·실패·인수 오류를 포함해 요청 전체 최대 8회다. 모델 호출은 에이전트 최대 9회와 독립 검토 최대 1회이며 전체 90초를 적용한다. `ToolCallLimitMiddleware`·`ModelCallLimitMiddleware`와 요청별 실행 검사를 함께 두고 한도 뒤에는 도구 없는 최종 응답만 허용한다. 그래프 단계 수 제한을 도구 횟수 제한으로 간주하지 않는다. 매 모델 호출에 전체 대화·도구 스키마와 응답 여유를 계산하며 체크포인터·자동 영구 저장·쓰기 도구는 추가하지 않는다.

`privacy.py`는 내장 `PIIMiddleware`의 이메일·신용카드·IP 탐지와 `redact` 전략을 재사용한다. 질문·도구 결과·생성된 도구 인수·답변을 정제하고 기존 문자열 모델 경로의 분류·근거 검토에도 적용한다. JSON의 문자열 값·키를 정제하며 SourceRef의 UUID·숫자 위치는 보존한다. SQLite 정본·revision·임베딩과 출처 패널은 바꾸지 않는다. 이름·전화번호·의미 기반 판정, 저장 허용 판단은 이번 범위 밖이다. 검증 범위와 한계는 [후속 계약](react-agent.md)에 기록한다.

## 확인한 공식 계약

- [SIWC OSS 로그인](https://developers.openai.com/siwc/token-sharing-open-source/sign-in): dynamic client 등록, PKCE·nonce, loopback callback.
- [모델과 추론](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference): 계정 카탈로그, public Responses endpoint, store=false/stream=true.
- [계정과 세션](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions): 계정별 등록·refresh·revocation.
- [MCP ASGI](https://py.sdk.modelcontextprotocol.io/run/asgi/), [MCP 사용자 확인](https://py.sdk.modelcontextprotocol.io/handlers/elicitation/): 부모 lifespan과 모델 입력 밖의 Resolve/Elicit.
- [LangChain 에이전트](https://docs.langchain.com/oss/python/langchain/agents), [내장 middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in): 모델·읽기 도구 루프, 호출 제한과 PII 탐지 구성.

실제 로그인 후 발견한 요청 형식 오류는 [SIWC preview 제한](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)에 맞춰 수정했다. 공급자 오류는 안전한 HTTP 상태·code·param·request ID만 구조화하며 원본 응답 본문·토큰은 노출하지 않는다. 답변의 관계 맥락도 내부 스냅샷으로 보관하고 철회·참조 변경 시 완료 전에 무효화한다.
