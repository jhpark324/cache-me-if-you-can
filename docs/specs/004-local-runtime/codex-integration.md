# Codex 기록 관리 연결

## 수용 기준

- 관리 스킬 원본은 `docs/skills/second-brain/SKILL.md`에 둔다. 설치 명령은 현재 Codex 사용자 스킬 디렉터리에 복사하고 프로젝트 밖의 다른 스킬을 변경하지 않는다.
- MCP는 기존 Streamable HTTP 엔드포인트를 사용한다. Codex 설정에는 주소와 로컬 헤더 제공 명령만 기록하며 bearer 값은 기록하지 않는다. 헤더 제공 명령은 앱 소유 `local-access.json`만 읽고 OAuth 인증 파일은 읽지 않는다.
- 설치는 기존 Codex 설정을 보존하며 동일 설정 반복 실행은 안전하다. 다른 `second_brain` 설정이 있으면 변경 전에 차이를 검사하고 명시적 교체 옵션으로만 갱신한다.
- 생성·정정은 요청한 내용만 저장하고 실제 저장 결과를 반환한다. 삭제는 미리보기와 실제 클라이언트 elicitation을 거치며 거부·취소·미지원은 삭제하지 않는다.
- 실제 Codex 도구 왕복, 프로그램이 대신 답한 elicitation 계약 검사, 실제 사람이 확인한 UI 검증을 서로 구분한다.

## 설계

공식 Codex의 `http_headers_helper`를 이용해 연결 시 보호된 토큰 파일을 읽는다. 부모 셸 환경 변수에 토큰을 미리 설정하거나 설정 파일에 평문 비밀을 복사할 필요가 없다. 실행 환경이 WSL이면 WSL Python을 사용하며 다른 호스트로 이동하면 해당 환경에서 설치 명령을 다시 실행한다.

스킬은 명시적 저장·정정·완료·삭제와 근거 조회를 안내한다. 공개 범위 기본값 `public`은 현재 공유 기능 활성화를 뜻하지 않는다. 검색 결과의 명령문은 데이터로 취급한다. 중복 가능성을 검색하더라도 사용자 요청 없이 자동 병합하거나 원기록을 삭제하지 않는다.

공식 설정 근거: [Codex MCP](https://developers.openai.com/codex/mcp), [설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference).

## Codex 0.164.0 삭제 확인 폼 호환성

MCP Python SDK 2.3.0은 `DeleteAnswer`의 JSON Schema에 루트 `title`을 생성한다. Codex가 사용하는 [Rust MCP SDK의 스키마](https://github.com/modelcontextprotocol/rust-sdk/blob/98a54789b80110ad210495c4ad845c89e1980471/crates/rmcp/src/model/elicitation_schema.rs#L1130)는 이 필드를 보존하지만, [Codex 0.164.0의 앱 서버 스키마](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/app-server-protocol/src/protocol/v2/mcp.rs#L440)는 루트의 `$schema`, `type`, `properties`, `required`만 허용한다. 따라서 [변환 실패 처리](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/app-server/src/bespoke_event_handling.rs#L900)가 사용자에게 폼을 전달하기 전에 `Cancel`을 반환한다. 도구 호출 권한 확인은 보이지만 제품의 삭제 확인은 보이지 않던 원인이다.

삭제 응답 모델의 스키마 생성 시 루트 `title`만 제거해 이 경계에 맞춘다. 필수 `delete: boolean`과 실제 사용자 확인, 거부·취소 시 삭제 차단은 유지한다. 전역 승인 정책을 변경하거나 빈 도구 권한 확인을 삭제 동의로 대체하지 않는다. 스키마 호환성 회귀, 실제 HTTP 왕복, 실제 Codex 왕복, 사람의 최종 확인은 각각 별도 검증으로 기록한다.
