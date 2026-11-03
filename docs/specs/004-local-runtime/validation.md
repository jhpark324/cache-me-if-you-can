# 로컬 제품 런타임 검증

- 실행일: 2026-11-02
- 환경: WSL Linux x64, Python 3.12.13, Node 22.22.1, CPU
- 상태: 요청한 후속 1~4번의 구현·로컬 검증 완료. 실계정 로그아웃 후 재로그인·네이티브 OS 검증은 남아 있어 기능 폴더는 `in-progress`다.

## 검증 시점

아래 표는 후속 1~4번 완료 당시 결과다. 홈 그래프·UX·리모트 이전 수정의 결과는 [최종 점검](final-review.md#검증-근거), 그 뒤 ReAct·답변·검색 그래프 개선은 각 후속 문서에 기록한다. 가장 최근 유형 단순화·데이터 확장 검증은 [여섯 유형·Codex 저장 시나리오](record-kinds-and-scenarios.md)를 따른다. 이전 수치는 당시 증거로 보존하며 최신 결과와 혼용하지 않는다.

## 후속 1~4번 검증 결과

| 범위 | 결과와 한계 |
| --- | --- |
| 전체 백엔드 | **148 passed, 0 skipped, 32.78초.** 실제 고정 KURE-v2 CPU 시험 포함. 도메인·인증·작업 경합·HTTP/MCP·질문 예산·취소·버전 무효화 검사 |
| 웹 | 빌드 성공. 계약 UI **19 passed**, 실제 서버 전용 **2 skipped**는 별도 실행으로 분리. 격리된 실제 API 통합 **2 passed**, JavaScript 오류 **0** |
| MCP | SDK 2.3.0, Streamable HTTP/SSE, 도구 **22개**와 모든 outputSchema 확인. 주제 재시도 도구 포함. 실제 Codex 0.164.0에서 스킬 탐색·생성·정정·조회·삭제 거부/승인 왕복 확인 |
| 로그인 운영 | 실제 계정 강제 토큰 갱신 성공, 모델 선택·로그인 유지, 서버 재시작·카탈로그 확인. 실제 앱에서 새 로그인 시도 시작→취소 후 기존 계정 유지 확인. 공급자 로그인 화면은 이 취소 검사에서 열지 않음 |
| 웹 관리 | 명시적 병합과 원본 보존, 충돌 시 초안 유지, 관계 생성·정확한 Unicode 구간·근거 조회·이유를 남기는 철회, 실패 주제 작업 재시도 확인 |
| 긴 본문 | 저장 한도 100,000 code points까지 연속 구간으로 처리. 중간 실패/수정/삭제/모델 변경 시 부분 주제 반영 금지. 전체 원문 복원·후반부 주제 반영은 자동 계약 검사이며 10만자 실모델 정확도 평가와는 구분 |
| 검색 평가 | 고정 합성 15기록·15사례. Hit@1 **100%**, macro Recall@5 **96.67%**, 실제 선택 맥락의 기대 출처 recall **100%**. 이 자료에서 질의 최대 64토큰·원문 구간 처리 준수 |
| 실제 답변 | 사용자 선택 `gpt-6-sol` 유지. 학습 원자성, AI 제안 미실행, 가짜 여권 정보/주입 문자열 무시 3사례에서 기대 출처와 의미 구분 확인. 각각 22.079/25.537/19.496초 |
| 실행 | 최신 코드로 8000 서버 재시작 후 HTTP 200·검색 준비·로그인·선택 모델 유지. Windows 호스트에서도 HTTP 200. Windows 네이티브 서버 실행 검증은 아님 |

기계 판독용 결과는 [전체 요약](artifacts/verification-summary.json), [실계정 갱신](artifacts/refresh-runtime-verification.json), [로그인 시도 취소](artifacts/login-cancel-verification.json), [현재 MCP 도구](artifacts/mcp-live-tools-verification.json)에 기록했다. 토큰·계정 이메일·client ID는 포함하지 않는다.

## Codex 실제 검증과 수정

[스킬 원본](../../skills/second-brain/SKILL.md)을 현재 Codex 사용자 디렉터리에 설치하고, 기존 설정을 보존하며 `second_brain` 연결을 등록했다. 공식 `http_headers_helper`가 연결 시 앱 소유 토큰을 읽는다. 설정 파일에는 토큰을 복사하지 않는다.

실제 Codex 연결에서 메모리 클라이언트 시험으로 발견하지 못한 두 문제를 수정했다.

1. JSON 전용 HTTP 응답에서는 서버의 삭제 확인 질문을 전달할 수 없어 SSE 응답으로 변경했다.
2. Python SDK가 만든 폼 스키마의 루트 `title`을 Codex 0.164.0이 거부해 UI 전달 전에 취소했다. 선택적 루트 `title`만 제거했다. 필수 boolean과 실제 확인 절차는 유지했다. [공식 소스 근거](codex-integration.md)를 참고한다.

[실제 Codex 검증 결과](artifacts/codex-verification.json)는 다음 범위를 증명한다.

- 임시 SQLite 서버를 별도로 실행하고 실제 Codex app-server로 스킬 탐색·생성·정정·재조회를 수행했다.
- 첫 삭제 확인에는 검증 클라이언트가 자동 거부를 보냈고 기록이 남았음을 확인했다.
- 실제 Codex 모델 turn이 스킬을 사용해 같은 임시 기록의 삭제를 요청했다. 제품 확인 질문을 이 대화에 전달하고 **사용자의 “검증용 기록 삭제 승인” 응답**을 클라이언트에 전달했다. 삭제 성공 후 재조회가 차단됨을 확인했다.
- 검증 도구의 실행 권한과 제품의 삭제 재확인은 분리했다. 사람이 승인한 것은 두 번째 제품 삭제 폼이다.
- 이는 실제 Codex 프로토콜과 사람의 응답 왕복 검증이다. Codex 네이티브 폼의 시각 렌더링/클릭 검증으로 확대하지 않는다.

사용자 저장소에는 검증 기록을 추가하지 않았다. 재현 도구는 [check_codex.py](../../../scripts/check_codex.py), 설치 방법은 [실행 가이드](../../guides/local-development.md)를 따른다.

## 구현별 근거

- [여섯 유형·Codex 저장 시나리오](record-kinds-and-scenarios.md): 기존 이력 호환·스킬 작성 원칙, 합성 대화 40개의 실제 MCP 저장·검색·출처 검증.
- [검색 상단 배치·검색 근거 그래프](retrieval-graph.md): 실제 읽은 구간·최종 인용의 임시 시각화, 출처 전체 좌표 선택, PII·변경 재검증, Canvas 유지와 화면 동선.
- [하나의 답변과 작은 출처](answer-reading.md): 별도 관련 기록 요청 제거, 자연스러운 설명과 작은 출처, 패널·초점 복귀.
- [ReAct 에이전트](react-agent.md): 자율 읽기 도구, 총 8회 제한과 개인정보 미들웨어.
- [UI·UX 점검·개선](ui-ux-refinement.md): 초안 유실 방지, 모바일/태블릿 메뉴·상세 초점/오류 복구, 그래프 선택/찾기, 도움말/반응형 보완. 최신 웹 46개·실제 API 3개와 시각 검증.
- [홈 그래프·이름 변경](home-graph-refresh.md): 003 시안과 실제 홈의 차이 수정, 제한된 실제 그래프 API, 검색/출처 공존, 새 이름·기존 로그인 보존과 최신 회귀/브라우저 검증.
- [기록 도메인](../002-record-management/validation.md): SQLite 정본·revision·멱등성·출처 의존성·소프트 삭제·백업 계약.
- [운영 후속](operations-followup.md): 긴 본문 분류, lease 갱신, 실패 재시도, refresh/logout/cancel·모델 변경 경합.
- [웹 후속](web-management-followup.md): 병합·관계·원문 구간 선택·재시도·모바일·실제 API 시험.
- [품질 후속](quality-followup.md): 원 질문 구간 추적·모델별 예산·평가 자료·실제 응답 판정.
- [검색 평가 원자료](quality-retrieval-results.json), [실제 모델 평가 원자료](quality-live-results.json): 합성 자료 hash·환경·사례별 결과. 사용자 원문은 포함하지 않는다.

이전 회차의 실제 로그인·합성 기록 응답과 빈 저장소 응답은 [초기 실계정 기록](artifacts/live-auth-verification.json)에 남아 있다. SIWC의 배열 input·store=false·stream=true를 적용하며 지원하지 않는 max_output_tokens를 보내지 않는다. 출력 제한은 수신 측에서 적용한다.

## 재현 명령

프로젝트 루트에서 실행했다. 모델 경로는 기존 고정 snapshot을 사용한다.

```sh
KURE_TEST_MODEL_PATH="<고정된 KURE-v2 snapshot 경로>" backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python scripts/check_codex.py --model-turn --human
```

프런트는 `frontend/`에서 실행했다.

```sh
npm run build
LD_LIBRARY_PATH=/tmp/second-brain-graph-preview-tools/browser-libs/usr/lib/x86_64-linux-gnu npm test
SECOND_BRAIN_INTEGRATION=1 SECOND_BRAIN_QA_DATA_DIR=/tmp/second-brain-web-followup-qa SECOND_BRAIN_TEST_URL=http://127.0.0.1:8010 LD_LIBRARY_PATH=/tmp/second-brain-graph-preview-tools/browser-libs/usr/lib/x86_64-linux-gnu npm test -- tests/integration.spec.ts tests/management-integration.spec.ts
```

`8010`은 격리된 QA 서버다. 실패 주제 작업의 UI 검증에서는 해당 테스트 기록의 작업만 failed로 시드하고 실제 API 재시도를 검사했다. 실제 모델이 실패한 사례로 주장하지 않는다. LD_LIBRARY_PATH는 이 WSL 브라우저 시험 환경에 필요한 설정이며 제품 실행의 필수값이 아니다.

## 화면 증거

- [데스크톱 관계 편집](artifacts/management-desktop-relations.png)
- [모바일 관계 편집](artifacts/management-mobile-relations.png)
- [데스크톱 기록·출처](artifacts/integration-desktop-source.png)
- [데스크톱 첫 화면](artifacts/integration-desktop-home.png)
- [모바일 첫 화면](artifacts/integration-mobile-home.png)

## 남은 외부 검증과 품질 한계

- 사용자가 “현재 로그인 유지, 검증은 나중에”를 선택하여 실제 원격 로그아웃/철회 후 재로그인은 명시적으로 보류했다. 원격 철회 성공/실패·요청 취소·늦은 callback·토큰 회전은 격리된 HTTP 계약 검사로 확인했다.
- Windows·macOS·Linux 네이티브 설치/CPU 실행/종료/ACL과 Intel Mac·Windows ARM 패키지 제약은 별도 5번 작업이다.
- Codex 네이티브 확인창의 실제 화면 렌더링은 미검증이다. 실제 app-server·모델·사람의 삭제 승인 왕복과 구분한다.
- 실카탈로그가 정확한 토크나이저를 제공하지 않아 입력 예산은 카탈로그 입력 창과 UTF-8 바이트 기반 보수 추정에 근거한다. 정확한 공급자 토큰 계수라는 뜻은 아니다.
- 실제 답변 3개 모두 의미·출처는 맞았지만 검색/맥락 예산의 한계를 전파해 `insufficient`로 판정했다. 보수적인 상태 판정과 중복 한계 문구, 복합 질문 순위는 후속 품질 조정 여지가 있다. 소규모 합성 평가를 일반 한국어 성능이나 SLA로 확대하지 않는다.
- 지연 로딩한 그래프 번들 약 1.19MB는 추가 최적화 여지가 있다.

## ReAct·PII 후속 변경

고정 검색 단계를 `create_agent`로 전환한 현재 구현·자동 검사·실계정 응답은 [ReAct 후속 검증](react-agent.md)을 따른다. 위의 이전 테스트 수·6질의 품질 수치를 새 에이전트의 결과로 해석하지 않는다.

## 하나의 답변·작은 출처 후속 변경

별도 관련 기록 요청을 제거한 현재 웹의 64개 회귀·실제 로그인 모델 응답·화면 검증은 [하나의 답변과 작은 출처](answer-reading.md)를 따른다. 이전 검증 기록을 덮어쓰지 않는다.
