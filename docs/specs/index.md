# 기능 명세 인덱스

기능을 시작하면 실제 생성한 문서와 상태를 이 인덱스에 등록한다.

| ID | 기능 | 상태 | 현재 범위 |
| --- | --- | --- | --- |
| 002 | [기록 저장·조회·정정·소프트 삭제](002-record-management/index.md) | `in-progress` | SQLite 도메인·공통 입출력·실제 Codex 확인 완료, 네이티브 OS 관문 남음 |
| 003 | [검정 배경 지식 탐색 디자인 프리뷰](003-knowledge-space-design/index.md) | `verified` | 흰색 본문·주황색 강조·어두운 유리 팔레트 확인. 검색·출처 목데이터 시안 |
| 004 | [로컬 제품 런타임](004-local-runtime/index.md) | `in-progress` | 통합·실계정·Codex 검증, 홈 그래프 복원과 Cache Me If You Can 이름 적용. 네이티브 OS 관문 별도 |

001 그래프 시안은 2026-11-02 사용자 요청으로 디자인 참고 기준에서 폐기해 활성 목록에서 제외했다. 라이브러리만 [ADR-004](../decisions/ADR-004-graph-visualization-library.md)로 채택했으며 세부 디자인은 별도로 진행한다. [폐기 안내](001-knowledge-graph-preview/index.md)와 [기술 실험 이력](../research/archived-graph-preview/index.md)을 보존한다. 기존 001 번호는 재사용하지 않는다.

## 기능 폴더 규칙

- 경로: `docs/specs/<세 자리 번호>-<kebab-case 이름>/`
- 기능 인덱스: `index.md` — 상태, 문서 목록, 관련 기능과 결정
- 명세: `spec.md` — 문제, 범위, 요구사항, 수용 기준
- 설계: `design.md` — 구현 방식과 영향 범위
- 작업: `tasks.md` — 실행 순서, 진행 상태, 수용 기준 연결
- 검증: `validation.md` — 수용 기준별 검증 결과와 근거

새 기능을 만들 때 [SDD 작업 절차](../guides/sdd-workflow.md)와 [템플릿 인덱스](../templates/index.md)를 참고한다. 다른 기능 문서는 의존 관계나 영향이 있을 때만 읽는다.

## 상태

`draft → ready → in-progress → verified`

- `draft`: 명세 작성 중이며 미정 사항이 남아 있다.
- `ready`: 범위와 수용 기준이 구현 가능한 수준으로 정리되어 있다.
- `in-progress`: 구현 또는 검증을 진행 중이다.
- `verified`: 범위 내 수용 기준의 검증을 마치고 근거를 기록했다.

상태는 진행 상황을 나타내며 별도의 사용자 승인 단계를 뜻하지 않는다. 기능 인덱스의 상태를 변경할 때 이 목록도 함께 갱신한다.
