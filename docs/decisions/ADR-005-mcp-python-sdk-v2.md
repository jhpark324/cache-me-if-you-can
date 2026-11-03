# ADR-005: 공식 MCP Python SDK v2 채택

- 상태: `accepted`
- 작성일: 2026-11-02
- 관련 설계: [기술 스택](../architecture/technology-stack.md), [서비스 계약](../architecture/service-contracts.md), [데이터 스키마](../architecture/data-schema.md)

## 배경

삭제 동작은 [ADR-006](ADR-006-soft-delete-without-trash.md)의 soft delete·조회 차단을 따른다. SDK는 제품의 삭제·출처 정책을 대신하지 않는다.

Python/FastAPI 구성에 맞춰 공식 MCP Python SDK v2를 선택한다. 프로토콜 자체의 날짜 버전과 SDK의 주 버전을 구분한다.

공식 SDK v2는 안정판이며 현재 규격 `2026-07-28`과 이전 클라이언트 규격을 지원한다. 프로토콜 버전은 `YYYY-MM-DD`, SDK 버전은 `2.x`, 메시지의 JSON-RPC 버전은 `2.0`이다. `MCP protocol v2`라는 별도 버전 문자열을 만들어 보내지 않는다. [공식 SDK](https://py.sdk.modelcontextprotocol.io/), [규격 버전](https://modelcontextprotocol.io/specification/versioning)

## 검토한 대안

| 대안 | 판단 |
| --- | --- |
| 공식 Python SDK v2 | Python/FastAPI 통합과 공식 규격 호환 경로를 활용하기 위해 채택 |
| SDK v1에 고정 | 이전 주 버전에 고정하는 별도 호환 요구가 없음 |
| 별도 FastMCP 패키지를 v2라는 이유로 선택 | 공식 SDK v2와 다른 패키지이므로 별도 의존성으로 채택하지 않음 |
| JSON-RPC 2.0만 직접 구현 | 전송·규격 호환·도구·확인 흐름을 SDK 없이 재구현할 필요 없음 |

## 결정

공식 `mcp` 패키지의 v2 계열과 Streamable HTTP를 사용한다. `MCPServer`로 공통 Pydantic 입출력 모델에 기반한 도구를 노출하고 FastAPI에 ASGI 앱을 통합한다. 기존 로컬 MCP CRUD·조회 역할은 유지한다.

구현 의존성은 [backend/uv.lock](../../backend/uv.lock)으로 고정한다. 이 결정에서 참조한 SDK 2.3.0의 릴리스와 배포 정보는 다음과 같다. [릴리스](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0), [PyPI](https://pypi.org/project/mcp/2.3.0/)

현재 규격 `2026-07-28`을 기준으로 설계하고 이전 규격 클라이언트 처리는 SDK의 호환 경로를 따른다. 현재 규격에는 예전 `initialize` 핸드셰이크·프로토콜 세션을 전제하지 않으며, 이를 앱의 도메인 상태나 웹 대화 수명과 혼동하지 않는다. SDK v2 채택이 실제 Codex가 모든 새 기능을 지원한다는 뜻은 아니다. [프로토콜 선택](https://py.sdk.modelcontextprotocol.io/protocol-versions/), [이전 클라이언트](https://py.sdk.modelcontextprotocol.io/run/legacy-clients/)

## 결과와 후속 조치

- FastAPI의 최상위 lifespan에서 SDK session manager 수명을 관리한다. 하위 ASGI 앱의 lifespan이 자동 실행된다고 가정하지 않는다. [통합 지침](https://py.sdk.modelcontextprotocol.io/run/asgi/)
- MCP와 웹의 도구/API는 같은 도메인 서비스와 스키마를 사용한다. SDK의 프로토콜 타입과 제품 DTO를 구분한다.
- 사용자 삭제 확인·버전 충돌·멱등성·권한·삭제 상태는 앱의 책임이다. SDK의 도구 힌트나 모델이 전달한 boolean만으로 사용자 확인을 대신하지 않는다.
- 실제 Codex에서 연결·도구 조회·구조화 출력·삭제 확인·오류·취소를 검증한다. 이 결정에서 연결 성공을 주장하지 않는다.
- 제품 스키마는 공통 Pydantic 계약으로 관리하고 웹/MCP 어댑터의 차이를 검증한다.

## 대체 관계

- 대체하는 결정: 기술 스택의 버전을 특정하지 않은 공식 Python SDK 추천을 v2 채택으로 구체화한다. 전송 방식과 기존 저장소·답변 실행 결정은 유지한다.
- 이 결정을 대체한 기록: 없음.
