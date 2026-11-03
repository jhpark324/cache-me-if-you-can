# 002 — 기록 저장·조회·정정·소프트 삭제

- 상태: `in-progress`
- 작성일: 2026-11-02
- 목적: Codex Skill과 자체 웹이 같은 기록을 저장·조회·정정하고, 사용자 재확인 후 soft delete하도록 공통 계약을 구현한다.
- 현재 진행: SQLite 기록 도메인·마이그레이션·공통 입출력 모델·웹/MCP 어댑터와 주제 작업 처리를 구현했다. 기록 시험 37개, 인증 계약 시험 25개, 런타임 시험은 이후 추가되어 현재 7개가 통과했다(004의 최종 전체 검사에 포함). 004에서 실계정 모델을 사용한 격리 합성 기록의 주제 연결·답변을 확인했으며, 이후 실제 Codex 삭제 확인 왕복은 [004 검증](../004-local-runtime/validation.md)에서 완료했다. 지원 OS별 왕복과 대표 주제 품질 평가는 남아 있다. 범위별 결과는 [검증](validation.md)에 기록한다.

## 문서

| 문서 | 읽는 시점 |
| --- | --- |
| [명세](spec.md) | 이 기능의 포함 범위와 수용 기준을 확인할 때 |
| [설계](design.md) | 저장 트랜잭션·조회 경계·변경 이력을 구현할 때 |
| [작업](tasks.md) | 구현 순서와 남은 작업을 확인할 때 |
| [검증](validation.md) | 수용 기준별 검증 방법과 실행 결과를 확인할 때 |

## 관련 문서

- 의존 기능: 없음. 첫 제품 기능이며 기존 001은 폐기한 그래프 시안의 이력이다.
- 제품 요구: [제품 기획](../../project/product-brief.md), [기록 유형](../../project/record-types.md), [기록·공개 범위](../../project/record-and-visibility.md)
- 공통 계약: [저장 스키마](../../architecture/data-schema.md), [MCP·웹 서비스 계약](../../architecture/service-contracts.md), [지식 계층](../../architecture/knowledge-layer.md)
- 저장 후 처리: [서버 주제 연결·Markdown 청크](../../architecture/ingestion-and-chunking.md). 002는 주제 연결 계약·작업·정합성을 다루고 청크 실행은 검색 후속 작업에서 검증한다.
- 통합 기능: [004 로컬 제품 런타임](../004-local-runtime/index.md)의 검색·맥락 선택·LangGraph 답변·웹 화면·그래프에 공통 기록 서비스를 제공한다.

실제 Codex의 삭제 확인 왕복은 004에서 확인했다. 지원 OS의 대표 흐름과 남은 수용 기준을 확인하기 전에는 `verified`로 표시하지 않는다. 자동 시험의 MCP 클라이언트는 실제 Codex 사용자 확인을 대신하지 않는다.
