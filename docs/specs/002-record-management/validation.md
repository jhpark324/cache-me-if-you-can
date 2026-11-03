# 기록 관리 검증

관련 명세: [spec.md](spec.md) · 상태: `in-progress` · 갱신일: 2026-11-02

## 대상·환경·실행 결과

- 대상: SQLite 정본·불변 revision·기록/Node/주제/출처/관계 서비스, 멱등성·삭제 확인·후속 작업, 공통 입출력 모델, HTTP와 MCP SDK 어댑터.
- 환경: Linux `6.18.54.1-microsoft-standard-WSL2`, x86_64, Python `3.12.13`, SQLite `3.53.1`. Windows 네이티브·macOS 실행 시험은 아니다.
- 패키지: SQLAlchemy `2.1.6`, Alembic `1.20.1`, FastAPI `0.162.0`, Pydantic `2.14.2`, MCP / mcp-types `2.3.0`, LangGraph `1.2.19`, pytest `9.2.0`. 잠금 파일: [uv.lock](../../../backend/uv.lock).
- 실제 파일 기반 임시 SQLite를 사용했다. 웹은 FastAPI TestClient, MCP는 SDK 메모리 클라이언트, OAuth는 RSA 서명과 HTTP MockTransport로 시험했다. 실제 Codex·실계정 로그인·원격 답변/주제 모델은 호출하지 않았다.
- 코드 기준: 2026-11-02 공유 워크스페이스. 이번 실행 시점의 Git 커밋 식별자는 없다.

저장소 루트에서 실행한 명령:

```bash
cd backend
.venv/bin/pytest tests/test_records.py tests/test_auth_contract.py tests/test_runtime.py -q
```

결과: **68 passed in 4.87s** — 기록 37개, 인증 계약 25개, 런타임 6개. 이후의 전체 검색·실모델 시험은 [004 검증](../004-local-runtime/validation.md)에 별도로 기록하며 이 결과에 합산하지 않는다.

## 시험 근거

| 기호 | 실제 시험 파일 | 확인한 범위 |
| --- | --- | --- |
| R | [test_records.py](../../../backend/tests/test_records.py) | 실DB CRUD·revision·Unicode Node·출처·주제·관계·멱등성·삭제·경합·마이그레이션·중첩 출력, 37개 |
| A | [test_auth_contract.py](../../../backend/tests/test_auth_contract.py) | RSA 서명·issuer/audience/nonce/만료·PKCE·계정 일치·토큰 갱신·미완료 모델 스트림 거부, 25개 |
| I | [test_runtime.py](../../../backend/tests/test_runtime.py) | 웹 세션/CSRF/삭제 세션 결합, 백업 제외 범위, 로그인 미준비 오류, MCP 미지원/모의 승인/재시도, 단일턴 LangGraph와 삭제 출처 재검증, 6개 |

**자동 검증 통과**는 적힌 자동 시험 범위에서 확인했다는 뜻이다. **부분 검증**은 일부 통과 근거가 있지만 AC의 추가 조합·실제 클라이언트·실모델 확인이 남았다는 뜻이다. 코드 존재만으로 통과 처리하지 않았다. 아래 함수 이름은 위 파일 안의 실제 테스트다.

## 수용 기준별 결과

| 기준 | 결과 | 실행 근거·확인 내용 | 남은 검증 |
| --- | --- | --- | --- |
| AC-001 | 자동 검증 통과 | R `test_minimal_create_is_atomic_and_returns_persisted_body`: 본문만 생성, public·미분류·완료 미추정, revision/receipt/색인·주제 작업 각 1행과 원문 대조 | 실제 Codex 저장은 AC-024 |
| AC-002 | 부분 검증 | R `test_strict_capture_validation`, `test_invalid_span_rolls_back_everything`, HTTP adapter 시험: 공백·unknown enum/필드·deleted_at 입력·100,001자·잘못된 Node 거부와 롤백, 한글/이모지 보존 | 모든 한도의 직전·정확값·초과 조합, 모든 오류별 receipt/outbox 행 대조 |
| AC-003 | 부분 검증 | R 최소 생성·PATCH 시험: 미분류·선택 필드 기본값·단일 유형·빈 목록 보존 | 아홉 유형의 다중 조합과 부분 날짜 전체 조합 |
| AC-004 | 자동 검증 통과 | R `test_output_models_validate_real_nested_domain_results`, `test_concepts_same_names_remain_distinct_and_manual_assignment`, 출처 상태 시험: 저장본·Node/주제·출처 상태를 실제 상세와 출력 모델로 검증 | 실제 화면·Codex 표시는 통합 시험으로 분리 |
| AC-005 | 부분 검증 | R `test_list_cursor_binds_filters_and_current_state`, 삭제 조회 차단 시험: 페이지 이동·필터/변경 후 cursor 무효화·삭제 제외 | 유형/주제 필터 조합·다중 revision 정렬·페이지 크기 전체 경계 |
| AC-006 | 자동 검증 통과 | R `test_unicode_codepoint_node_source_and_stale_transition`, `test_metadata_equivalence_remaps_node_without_changing_stored_ref`, 삭제 조회 시험: 정확한 과거 본문/span, 옛 node_get 거부, 원래/해석된 참조 분리, 삭제 후 이력 차단 | 미래 공유는 범위 밖 |
| AC-007 | 자동 검증 통과 | R `test_concurrent_writes_do_not_overwrite`, PATCH·불변 revision 시험: 같은 버전의 병렬 수정 중 한 번 커밋, 나머지 충돌, 과거 본문 수정 거부 | 다른 OS의 파일 잠금 동작 |
| AC-008 | 자동 검증 통과 | R `test_patch_omission_null_and_visibility_only`, 출처·Node 상태 시험: 제목 null·유형/Node 빈 배열·visibility 유지·sources 빈 배열의 의존성 유지 | 선택 필드의 전체 조합은 T-012 |
| AC-009 | 구현·전용 시험 미실행 | [records.py](../../../backend/src/second_brain/records.py)에 completion_change/edit 분기가 있음 | 완료 단독·본문 혼합 변경의 revision/change_kind 전용 대조 |
| AC-010 | 자동 검증 통과 | R `test_idempotency_replay_and_fingerprint_conflict`: 같은 요청 재생·다른 payload 충돌·다른 ID의 같은 본문 별도 저장 | 실제 네트워크 응답 유실은 AC-023 |
| AC-011 | 부분 검증 | R `test_merge_keeps_sources_and_originals`: 대상에만 새 revision, 출처와 옛 대상 본문 유지 | 병합 중 출처 변경·잘못된 기대 버전·커밋 단계별 실패 |
| AC-012 | 부분 검증 | R 주제 작업 원자 반영·동명 후보 보류·최소 생성 시험: ID 조회 없는 저장, 서버 주제 생성, 모호한 동명 후보 미연결 | 실제 모델 의미 판단·주제 없는 검색은 004와 연계 |
| AC-013 | 부분 검증 | R Unicode·범위 초과·명시적 주제 정정 시험: code point 추출·Node 범위 오류 거부·Node별 별도 주제 | 다른 revision Node·다른 brain Concept 정정 입력의 전체 조합 |
| AC-014 | 부분 검증 | R Node stale·범위 롤백 시험: 본문 변경 시 옛 span 제거·stale 유지·명시적 빈 구조 absent | stale 뒤 유효한 새 Node 재제출 전용 왕복 |
| AC-015 | 자동 검증 통과 | R `test_upstream_change_and_patch_cannot_clear_dependencies`, `test_provenance_cycle_and_cross_brain_are_rejected`, 삭제 조회 시험: 변경/삭제/상위 무효 상태·순환/타 brain 거부·파생 본문 보존 | 깊은 의존 그래프의 부하 시험 |
| AC-016 | 부분 검증 | R `test_source_review_rewrite_and_history`: 같은 본문의 단순 의존성 제거 거부, 재작성 후 새 집합·옛 본문/출처 보존 | A1→A2 동일 Capture 출처 교체·재검토 중 출처 경합 |
| AC-017 | 부분 검증 | R 삭제 준비·출력 모델 시험: 대상/버전/토큰/만료 필드와 삭제 전 본문 유지 | 발급 시각 기준 정확한 5분 경계·준비만 수행한 후 모든 상태 행 대조 |
| AC-018 | 부분 검증 | R 확인 capability·다른 세션·만료·버전 충돌·HTTP boolean bypass 시험, I MCP 시험: 토큰 단독·모델 boolean·확인 미지원 차단 | 실제 Codex 확인/취소·실사용 웹 확인 왕복 |
| AC-019 | 부분 검증 | R 삭제 시험, I `test_web_security_and_delete_session_binding`, `test_mcp_confirmation_is_hidden_and_required`: 확인 후 삭제·excluded·정본/Node/출처 내부 보존 | 실제 사용자 확인과 삭제 트랜잭션 각 단계의 장애 주입 |
| AC-020 | 부분 검증 | R `test_delete_hides_body_history_nodes_sources_and_receipt`, `test_deleted_relation_endpoint_cannot_leak_through_replay`, I 웹 삭제: 목록·상세·이력·출처·Node·관계·수정·receipt 차단 | 삭제 후 병합·재검토·모든 우회 인수의 개별 통합 시험 |
| AC-021 | 부분 검증 | R 삭제/receipt와 I MCP 재시도: 동일 삭제 요청 재실행 없이 재생, 삭제 전 생성 receipt는 unavailable로 본문 차단 | 삭제 전 수정 receipt·실제 응답 유실의 별도 조합 |
| AC-022 | 부분 검증 | R `test_provenance_cycle_and_cross_brain_are_rejected`: 같은 파일의 다른 brain에서 기록 조회·출처 생성 거부 | Concept·Node·Relation·모든 변경 경로의 타 brain 조합 |
| AC-023 | 부분 검증 | R 최소 저장 행 생성·잘못된 span 롤백·멱등 재생·index pending 반환 확인 | 커밋 단계별 장애·실제 네트워크 유실. 늦은 Lance 작업은 [004 검증](../004-local-runtime/validation.md) 근거를 따름 |
| AC-024 | 부분 검증 | R HTTP·중첩 출력, I MCP 확인 시험: 공통 서비스 저장/조회/삭제, 숨김 확인 의존성·미지원·모의 승인·replayed. HTTP response_model와 MCP outputSchema 제공 | 실제 Codex 도구/오류/정정/확인/취소 왕복, 모든 동작의 양쪽 어댑터 동일 입력 대조 |
| AC-025 | 부분 검증 | R 메타데이터 동등성과 `test_supersedes_requires_scoped_evidence_and_rejects_cycle`: Node 대응·범위/근거 없는 대체 거부·대체 순환 거부 | 주제 수정 후 관계 승계와 내용 변경의 전체 관계 조합 |
| AC-026 | 부분 검증 | R `test_relation_retraction_is_idempotent_and_does_not_change_capture`, 삭제 관계 replay 시험: 최초 철회·재시도·다른 이유 거부·조회 제외·기록 revision 유지 | 동시 철회·빈 이유·철회 시 삭제된 근거의 개별 시험 |
| AC-027 | 부분 검증 | R 주제 실패/동명 후보 시험: AUTH_REQUIRED 상태·본문 보존·needs_review. A의 25개는 OAuth/스트림 경계이며 주제 모델 성공 근거가 아님 | 실계정 미연결/호출 실패의 작업자 왕복·같은 job 재시도 전체 과정 |
| AC-028 | 부분 검증 | R `test_concept_worker_applies_atomically_no_recursion`, `test_late_concept_worker_does_not_overwrite_manual_assignment_or_delete`: 단일 새 revision·중복 적용·재귀 방지·수동 정정/삭제 뒤 늦은 결과 거부 | 실제 모델 지연·동시 새 주제 생성·본문 수정만의 독립 경합 |
| AC-029 | 부분 검증 | R 명시적 기록/Node 주제 정정·늦은 작업 시험: 별도 연결·빈 목록·ready·옛 자동 결과 차단 | 전체 Node 생략/빈 목록 조합·이전 연결 불변·타 brain Concept 주입 |

## 마이그레이션·출력 추가 검증

- R `test_alembic_baseline_applies_idempotently`: 고정된 0001을 두 번 실행한 뒤 실제 저장, 버전 행과 `PRAGMA foreign_key_check` 확인.
- R `test_migration_helper_adopts_only_matching_unversioned_schema`: 일치하는 create_all DB 편입 후 본문 보존, 새 DB 업그레이드, 알 수 없는 기존 스키마 중지 및 데이터 유지.
- R `test_output_models_validate_real_nested_domain_results`: 실제 생성·목록·상세·Node·출처·주제·관계·철회·삭제 결과를 Pydantic 모델로 검증.
- R `test_output_envelope_enforces_exclusive_success_and_failure_branches`: data/error 동시 출력 거부와 JSON Schema 배타성 확인. unavailable mutation의 본문·참조 노출도 출력 모델에서 제한한다.

## 남은 문제와 제약

- T-011 실제 Codex 확인·취소·오류 왕복과 T-013 Windows 네이티브/macOS/Linux 대표 흐름이 남아 있어 `in-progress`를 유지한다.
- 기록 37개는 모든 AC 조합의 전수 검증이 아니다. 완료 변경·출처 교체·실제 장애·관계 경합 등은 T-012에서 보완한다.
- 주제 LangGraph 작업자는 연결됐지만 실계정 모델의 의미 분류·동명 후보 판단 품질은 미검증이다. T-014를 완료 처리하지 않는다.
- 웹 요청 검증·MCP SDK 모의 승인·인증 계약 시험은 실제 사람의 삭제 확인이나 공급자 호환성 시험을 대신하지 않는다. 확인 없는 삭제 우회로 통과 결과를 만들지 않았다.
- 모델·검색·화면·백업 전체 통합과 OS 설치 상태는 [004](../004-local-runtime/validation.md)에서 확인한다.
