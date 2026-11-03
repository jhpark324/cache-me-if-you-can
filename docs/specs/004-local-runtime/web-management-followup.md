# 웹 기록 관리 후속 구현

- 상태: 웹 구현·자동/격리 실제 API 검증 완료. 실계정 모델 품질·네이티브 OS 검증과 구분한다.
- 기준: [004 명세](spec.md), [002 명세](../002-record-management/spec.md), [공통 계약](../../architecture/service-contracts.md)
- 범위: 사용자가 요청한 남은 웹 관리 동선. 기존 API의 저장 의미를 변경하지 않는다.

## 수용 기준

| ID | 동선 | 기대 결과 |
| --- | --- | --- |
| WEB-001 | 현재 기록에서 명시적으로 다른 기록을 병합 | 현재 기록을 대상으로 표시하고 검색·원문 확인으로 출처를 선택한다. 사용자가 편집한 최종 Markdown과 기대 버전으로 병합한다. 원본 기록은 유지하며 실제 저장 결과를 표시한다. |
| WEB-002 | 병합 대상/출처가 변경되거나 요청 실패 | 자동 덮어쓰기 없이 오류와 초안을 보존한다. 같은 내용의 재시도는 같은 request_id를 사용하며, 변경한 요청은 새 ID를 사용한다. |
| WEB-003 | 관계 작성 | 시작·대상·근거 기록을 검색/본문 확인으로 고르고 방향과 의미를 명시한다. ID나 JSON 직접 입력을 요구하지 않는다. 자동 유사도에서 관계를 생성하지 않는다. |
| WEB-004 | 조건 대체 관계 작성 | 새 조건→이전 조건을 표시한다. 시작·대상·근거의 정확한 본문 구간 또는 Node를 선택하고 범위/근거 설명을 필수로 받는다. Unicode code point span을 사용한다. |
| WEB-005 | 관계 조회·철회 | 서버가 조회 가능한 현재 관계만 보여준다. 끝점과 근거의 저장본을 확인할 수 있고 비어 있지 않은 이유로 철회한다. 기록 삭제로 표시하지 않으며 성공 후 현재 목록을 새로 읽고 이전 그래프를 무효화해 다음 열기에서 재조회한다. |
| WEB-006 | 주제 연결 실패/재검토 상태 | 저장본문과 별개 상태를 표시하고 명시적인 주제 재분류 요청을 보낸다. 진행 상태를 갱신하며 충돌/실패를 성공으로 표시하지 않는다. `POST /captures/{id}/concept-retry`에 현재 job_id·기대 버전·request_id를 전송한다. failed만 재시도하고 needs_review는 기존 주제 정정으로 연결한다. |
| WEB-007 | 입력·모달·모바일 | 기존 검정/흰색/주황색 유리 스타일과 키보드/축소 모션 지원을 유지한다. 닫기와 오류 상태에서 초점·입력 보존을 확인한다. |
| WEB-008 | 로그인 시도 취소 | settings의 세션별 `auth.pending_login`일 때만 취소 버튼을 표시하고 `/auth/cancel`을 호출한다. 이미 연결된 계정의 로그아웃과 구분한다. |

## 구현 설계

- `frontend/src/RecordConnections.tsx`: 검색 가능한 기록 선택, 원문/Node/범위 선택, 병합, 관계 생성·철회.
- 현재 상세의 `CaptureView` 버전을 편집 시작 시 보존하고 공통 서비스 계약의 기대 버전·SourceRef를 전송한다. 병합은 현재 기록에만 새 revision을 만든다.
- 본문 구간 선택은 읽기 전용 원문 textarea의 선택 위치(UTF-16)를 Unicode code point 수로 변환한다. 숫자 span 입력을 사용자에게 요구하지 않는다. 같은 문자열이 반복되면 실제 선택 위치를 사용한다.
- 관계에 보이는 제목/본문은 `source_get`으로 다시 읽는다. 조회 실패 시 저장된 제목을 우회 노출하지 않는다. 관계 철회 후 목록·그래프·답변 표시를 갱신한다.
- 재시도 요청의 request_id는 payload fingerprint가 유지되는 동안 보존한다. 저장 성공은 실제 MutationResult를 통해 표시한다.

## 검증 계획

Playwright 계약 시험으로 병합 본문/버전/멱등 요청, 관계 방향·구간·철회 이유, 주제 재시도 상태와 오류, 모바일 모달을 검증한다. 격리된 실제 SQLite 서버에서 병합 후 원본 유지, 관계 생성→조회→철회, 한글·이모지 구간을 검증한다. 실계정 모델 재분류 품질·실제 Codex 왕복·네이티브 OS 결과를 UI 자동 시험으로 대신하지 않는다.

## 실행 결과

- `npm run build`: TypeScript 검사와 Vite 제품 번들 성공. 3D 그래프는 동적 import이며 큰 별도 번들 경고를 숨기지 않았다.
- `LD_LIBRARY_PATH=/tmp/second-brain-graph-preview-tools/browser-libs/usr/lib/x86_64-linux-gnu npm test -- --output=/tmp/second-brain-web-full-followup`: 계약 브라우저 시험 19개 통과, 실제 서버를 요구하는 시험 2개는 이 명령에서 제외됨(28.4초). 기존 13개와 후속 6개를 함께 검사했다.
- 후속 계약 시험 6개는 병합 충돌/초안/멱등성, 관계 방향·근거·철회, 이모지 포함 정확 구간, 실패 작업의 같은 job 재시도, 모바일 모달, 기존 계정을 유지하는 로그인 시도 취소를 검사했다.
- 격리 서버 `http://127.0.0.1:8010`, 데이터 `/tmp/second-brain-web-followup-qa`에서 후속 실제 API 시험 1개 통과(6.4초): 해당 테스트에서 만든 주제 작업만 failed로 시드한 뒤 실제 재시도 API로 pending·동일 job/본문/revision을 확인했다. 이는 실제 모델 호출 실패를 재현한 시험이 아니다. 미로그인 상태의 정상 작업은 pending에 유지된다.
- 최종 회귀 실행은 `npm test -- tests/integration.spec.ts tests/management-integration.spec.ts`에 아래 환경변수를 적용해 기존 실제 CRUD/출처/백업과 후속 관리를 함께 검사했고 **2개 모두 통과**했다(13.7초).
- 같은 실제 시험에서 대상만 병합된 새 revision과 출처 원본의 불변, 한글·이모지 구간의 supersedes 생성·근거 원문 조회·이유 있는 철회·현재 관계 목록 제외를 확인했다. 브라우저 JavaScript 오류 0개, 390px 모바일 가로 넘침 없음.
- 실제 관계 화면 캡처: `frontend/test-results/management-desktop-relations.png`, `frontend/test-results/management-mobile-relations.png`. 004 공통 검증 기록이 장기 보관 경로를 관리한다.

위 명령은 저장소의 `frontend/`에서 실행했다. 실제 서버 시험은 아래처럼 명시적인 격리 DB 경로가 있어야 실행된다. 테스트는 새로 만든 기록의 job만 fixture 상태로 바꾸며 제품의 기본 데이터 경로를 사용하지 않는다.

```bash
SECOND_BRAIN_INTEGRATION=1 \
SECOND_BRAIN_QA_DATA_DIR=/tmp/second-brain-web-followup-qa \
SECOND_BRAIN_TEST_URL=http://127.0.0.1:8010 \
LD_LIBRARY_PATH=/tmp/second-brain-graph-preview-tools/browser-libs/usr/lib/x86_64-linux-gnu \
npm test -- tests/management-integration.spec.ts
```

설정의 로그인 취소 UI는 계약 fixture로 확인했고 취소 API 자체의 실제 인증 계약 검증은 백엔드 기록을 따른다. 이 문서는 실제 사용자 계정의 재분류 성공, 실제 Codex 사용자의 삭제 확인, Windows/macOS 네이티브 실행을 검증했다고 주장하지 않는다.
