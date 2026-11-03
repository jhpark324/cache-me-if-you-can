# 운영 안정성 후속 명세·검증

- 상태: 구현·자동 검증·실계정 강제 갱신 완료, 실제 로그아웃은 수동 관문
- 작성일: 2026-11-02
- 관련: [004 명세](spec.md), [저장 후 주제 연결](../../architecture/ingestion-and-chunking.md), [서비스 계약](../../architecture/service-contracts.md)

## 변경 범위와 수용 기준

1. **장문 주제 연결:** 저장 한도인 100,000 Unicode code points까지 원문 전체를 누락 없이 연속 구간으로 나눠 분류한다. 각 구간은 원문의 정확한 `[start,end)`와 문자열을 사용한다. 구간별 제안을 합쳐 검토한 뒤 현재 revision/상태/후보 버전을 다시 검사하고 한 번만 반영한다. 한 구간의 실패·취소·예산 초과는 전체 작업 실패이며 부분 주제 연결·본문 변경을 커밋하지 않는다.
2. **제한된 실행:** 구간별 최대 12,000 code points, 문단·줄 경계를 우선하되 원문 공백/Unicode를 다시 쓰지 않는다. 최대 20구간과 최종 통합 1회, 전체 720초를 작업 상한으로 사용한다. 기존 120초 lease는 구간 처리 중 갱신하며 모델 호출 동안 DB 트랜잭션을 열지 않는다. 자동 재시도는 같은 작업의 최대 3회다. 만료된 마지막 lease는 failed로 남긴다.
3. **명시적 재시도:** `POST /api/v1/captures/{id}/concept-retry`와 공통 `retry_concepts` 서비스는 `{request_id,capture_id,expected_revision_id,expected_state_version,job_id}`를 받는다. 현재 기록의 실패한 작업만 같은 job으로 pending 전환하고 시도 횟수·lease·오류를 초기화한다. 응답은 `MutationResult`다. 본문·revision·state_version·색인 세대는 바꾸지 않는다. 동일 요청 재시도는 receipt로 중복 초기화를 막는다. 삭제는 NOT_FOUND, 기대 버전/작업 불일치는 VERSION_CONFLICT, 실패 상태가 아니면 JOB_NOT_RETRYABLE(HTTP 409)이다.
4. **인증 경계:** 갱신은 한 계정에 대해 직렬화하며 검증한 새 토큰만 원자적으로 저장한다. 공급자 거부와 일시 네트워크 실패를 구분한다. 내부 `access_token(force_refresh=True)`로 저장된 만료 시각을 바꾸지 않고 명시적으로 한 번 갱신할 수 있다. 로그아웃은 로컬 자격 증명을 먼저 제거하고 진행 중 로그인 state를 무효화하여 늦은 callback이 재로그인시키지 못하게 한다. 원격 철회 실패는 별도 결과로 표시하며 로컬 로그아웃을 되돌리지 않는다. `POST /api/v1/auth/cancel`은 해당 웹 세션의 pending/in-flight 로그인만 무효화하고 기존 계정을 유지한다. `GET /api/v1/settings`의 `auth.pending_login`으로 현재 세션의 진행 상태를 표시한다.
5. **모델 메타데이터:** 공개 카탈로그에 명시된 입력창/출력 한도/토크나이저 필드만 안전하게 보존한다. `model_metadata()`는 알려진 값과 미제공 값을 구분하며 미제공 값을 모델의 실제 한도로 추정하지 않는다.
6. **모델 변경 경합:** 질문과 긴 주제 작업은 시작 모델을 고정한다. `generate_for_model`은 요청 전·토큰 획득 뒤·스트림 중·반환 전에 선택 모델과 세대를 확인한다. 모델을 바꿨다가 되돌려도 이전 작업을 완료하지 않는다. 웹 설정에서 모델을 바꾸면 진행 중 질문을 취소하며 이전 예산으로 새 모델을 호출하지 않는다.

## 장문 처리 설계

저장 원문은 수정하지 않는다. 각 분류 요청에는 해당 본문 구간과 겹치는 Node의 ID·의미·원래 범위, 기록의 힌트, 서버가 조회한 주제 후보만 포함한다. Node의 실제 텍스트는 해당 구간 본문으로 확인하며 원문의 Node를 자동 생성·수정하지 않는다. 모든 구간 제안을 통합하는 단계에서 기록 주제와 Node 주제를 구분하고, 같은 이름이지만 의미가 다른 제안은 자동 병합하지 않는다. 마지막 구간까지 처리한 경우에만 통합·커밋한다. 통합 응답은 전체 구간 번호를 빠짐없이 포함해야 하며 구간에 없던 신규 주제는 거절한다. 통합에서 연결하지 않은 제안은 미해결 힌트로 남겨 `needs_review`로 표시한다. 본문이 짧으면 기존 단일 분류 경로를 유지한다.

이 분할은 주제 분류용이다. 검색 임베딩의 Markdown/512토큰 청크와 같은 단위라고 주장하지 않는다. 분류 결과의 의미 품질은 별도 평가 대상이며 원문 전체를 읽었다는 실행 근거와 구분한다.

## 검증 계획

- 20,000자 초과·100,000자·CRLF·이모지·결합문자를 포함해 구간 연결이 원문과 정확히 같고 후반부 주제가 반영되는지 확인한다.
- 중간 구간 실패·동일 작업 중복·분류 중 수정/삭제·lease 만료·명시 재시도 중복을 실제 임시 SQLite에서 시험한다. 부분 연결이나 중복 revision이 없어야 한다.
- RSA/HTTP MockTransport로 refresh 동시 호출·회전·응답 형식/계정 불일치·일시 오류·철회 성공/실패·callback과 logout/cancel 경합을 재현한다. 비밀정보가 응답·오류에 없어야 한다.
- 실제 계정의 강제 갱신·로그아웃은 사용자 로그인 상태와 회전 토큰을 바꾸므로 격리 검증과 구분한다. 현재 사용자 자격 증명을 복제하거나 강제로 만료·철회하지 않는다.

## 실행 결과

2026-11-02, 기존 WSL2·Python 3.12 환경에서 다음 명령을 실행했다. 모델 호출은 결정적 대체 모델, 인증은 격리된 임시 자격 증명과 HTTP MockTransport를 사용했다.

```bash
cd backend
.venv/bin/pytest tests/test_operations.py tests/test_auth_operations.py tests/test_auth_contract.py tests/test_records.py tests/test_runtime.py tests/test_question_relations.py -q
```

모델 변경 회귀까지 포함해 **110개 통과**했다. 신규 운영 시험은 [test_operations.py](../../../backend/tests/test_operations.py) 15개와 [test_auth_operations.py](../../../backend/tests/test_auth_operations.py) 21개다. 기존 인증·기록·런타임·관계 재검증 회귀도 함께 통과했다.

| 항목 | 실제로 확인한 결과 |
| --- | --- |
| 장문 전체 처리 | 20,001자·100,000자 본문 전체를 분류 요청에 전달하고 마지막 구간에만 있는 주제를 반영. 원문과 과거 revision 유지, 새 revision 하나만 생성 |
| Unicode·구간 | 한글·이모지·결합문자·CRLF 구간의 정확한 원문 복원, 연속 위치와 12,000자 상한 |
| Node 주제 | 후반부 Node에만 연결한 주제가 기록 전체에 복제되지 않음 |
| 실패·경합 | 중간 요청 실패·통합에서 구간 누락은 전체 실패, 부분 Concept/연결 커밋 없음. 분류 중 사용자 정정은 옛 lease를 superseded로 처리 |
| 누락 제안 | 모델의 통합 결과에서 빠진 구간별 주제는 `needs_review`·미해결 힌트로 노출 |
| 재시도 | 같은 job·본문/revision 유지, 명시적 요청의 멱등성, running/옛 버전 거부, 만료된 마지막 lease의 failed 전환, HTTP 409/정상 응답 |
| 갱신 | 동시 세 요청의 refresh 한 번, 토큰 회전, 유효 토큰의 명시적 강제 갱신, 일시 실패의 기존 자격 보존, invalid_grant 정리, 잘못된 만료 값의 부분 반영 차단 |
| 로그아웃 | 원격 철회 성공/실패, 원격 요청 취소 어느 경우에도 로컬 토큰은 이미 제거됨 |
| 로그인 취소 | 세션별 취소, 기존 로그인 유지, callback 처리 중 cancel/logout/새 로그인 뒤 낡은 결과 반영 차단, CSRF·pending 상태 API |
| 카탈로그 | 명시된 숫자 한도만 보존하고 미제공 input/output/tokenizer를 추정하지 않음. 임의 공급자 필드를 공개 상태에 복사하지 않음 |
| 모델 변경 | 예산 모델과 현재 선택 불일치 시 공급자 요청 전 차단. 토큰 획득 도중·스트림 도중 모델 변경, 다른 모델 선택 후 원래 모델 복귀, 스트림 중 로그아웃 모두 부분 응답을 반환하지 않음 |

구현 근거: [주제 작업자](../../../backend/src/second_brain/enrichment.py), [기록 작업/lease/retry](../../../backend/src/second_brain/records.py), [입력 계약](../../../backend/src/second_brain/schemas.py), [웹 어댑터](../../../backend/src/second_brain/api.py), [인증](../../../backend/src/second_brain/auth.py).

## 실제 계정의 갱신 확인

루트 통합 작업에서 기존 실행 서버를 정상 종료한 뒤 단일 소유 프로세스로 `access_token(force_refresh=True)`를 한 번 실행했다. 강제 갱신 성공·선택 모델 유지·서버 재시작·카탈로그 준비·`connected=true`를 확인했다. 만료 시각을 강제로 수정하지 않았으며 토큰 값과 계정 식별자는 문서에 저장하지 않았다. [비밀을 제외한 실행 기록](artifacts/refresh-runtime-verification.json)을 근거로 삼는다.

실행 중인 8000 앱의 별도 웹 세션에서 새 로그인 시도 시작→pending 확인→취소→pending 해제를 확인했고 기존 로그인과 선택 모델을 보존했다. [실행 기록](artifacts/login-cancel-verification.json)에 공급자 로그인 화면을 열지 않았다는 범위도 남겼다. 실패 주제 재시도는 웹 외에 MCP `capture_retry_concepts`에서도 같은 서비스로 제공한다.

## 남은 외부 관문

- 자동 시험은 격리된 자격 증명을 사용했고, 실제 강제 갱신은 위의 별도 실행으로 확인했다. 공급자 갱신 장애·계정 변경 등 모든 외부 상황을 한 번의 성공으로 검증했다고 주장하지 않는다.
- 실제 공급자 로그아웃/철회 뒤 재로그인은 사용자의 “현재 로그인 유지, 검증은 나중에” 선택에 따라 보류했다. 공급자 응답·취소·네트워크 경합은 격리 HTTP 시험으로 검증했다.
- 100,000자 전체를 읽는 처리 경로와 원자성은 통과했지만, 실제 장문에서 모델이 고른 주제의 의미 품질은 별도 실계정 자료 평가다. 문자 한도 전체의 누락 없는 처리와 의미 정확도를 같은 결과로 기록하지 않는다.
