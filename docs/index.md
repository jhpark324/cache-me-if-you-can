# 문서 인덱스

**Cache Me If You Can**의 문서 진입점이다. **현재 작업에 해당하는 행을 선택하고 필요한 문서만 읽는다.** 각 하위 인덱스는 탐색용이며, 연결된 모든 문서를 읽으라는 지시가 아니다.

처음 실행하려면 [프로젝트 소개](README.md), 현재 구현과 후속 검증을 확인하려면 [로컬 런타임 인덱스](specs/004-local-runtime/index.md), 리모트 등록 전 점검 범위는 [2026-11-03 최종 점검](specs/004-local-runtime/prepublish-review-2026-11-03.md)을 읽는다.

| 작업 | 진입 문서 | 읽는 시점 |
| --- | --- | --- |
| 프로젝트 목적·범위 확인 | [프로젝트](project/index.md) | 처음 프로젝트를 파악하거나 제품 방향을 바꿀 때 |
| 기능 명세 작성·구현·수정·검증 | [기능 명세](specs/index.md) | 해당 기능을 작업할 때 |
| 공통 구조·기술 스택 확인 | [아키텍처](architecture/index.md) | 여러 기능에 영향을 주는 설계를 할 때 |
| 기존 설계 결정·이유 확인 | [결정 기록](decisions/index.md) | 관련 결정을 재사용하거나 변경할 때 |
| 전체 작업 순서·의존성 확인 | [작업 계획](plans/index.md) | 기능 간 우선순위와 연동·배포 검증 순서를 확인할 때 |
| PR 작성·검토 | [PR 작성 규칙](guides/pull-request-convention.md) · [PR 템플릿](pull_request_template.md) | 표준 제목과 한글 단답형 설명을 작성할 때 |
| Codex 기록 관리 스킬 | [에이전트 스킬](skills/index.md) | 저장·조회·정정·삭제 스킬을 설치하거나 유지보수할 때 |
| 디자인 시안 확인·수정 | [프로토타입](prototypes/index.md) | 목데이터 화면과 디자인 검토 범위를 확인할 때 |
| 서비스 소개 화면 확인 | [소개용 시각 자료](assets/index.md) | README의 실제 제품 스크린샷과 촬영 범위를 확인할 때 |
| 초기 조사 자료 확인 | [조사 자료](research/index.md) | 설계 배경과 비교 대안을 확인할 때 |
| SDD 절차·문서 작성 규칙 확인 | [작업 가이드](guides/index.md) | 새 기능을 시작하거나 절차가 필요할 때 |
| 새 문서 생성 | [템플릿](templates/index.md) | 필요한 유형의 문서를 만들 때만 |

## 구조

```text
AGENTS.md                    # 에이전트 진입점; 루트 문서의 유일한 예외
docs/
  index.md                   # 전체 문서 탐색
  project/index.md           # 제품 기획과 저장·공개 범위의 설계안
  plans/index.md             # 기능 간 작업 순서·의존성·검증 관문
  specs/index.md             # 기능 목록과 상태
  prototypes/index.md        # 목데이터 디자인 시안과 검토 범위
  assets/index.md            # README용 실제 제품 화면과 촬영 범위
  architecture/
    index.md                 # 공통 구조와 기술 기준
    knowledge-layer.md       # 에이전트용 지식 계층 설계
    data-schema.md           # SQLite·LanceDB 논리 스키마
    service-contracts.md     # MCP·웹 공통 입출력 계약
    ingestion-and-chunking.md # 서버 주제 연결·Markdown 청크 규칙
    retrieval-and-context.md # Node 검색과 에이전트 맥락 활용 계약
    schema-fit-review.md     # 서비스 적합성 판단과 구현 전 보완점
    technology-stack.md      # 기술 스택 선정과 추천
    search-and-embedding.md  # LanceDB와 CPU 임베딩 설계
    platform-support.md      # 운영체제·CPU 아키텍처 지원과 검증
  decisions/index.md         # ADR 목록
  research/index.md          # 초기 보고서와 참고 범위
  guides/
    index.md
    sdd-workflow.md          # 명세 → 설계 → 작업 → 검증 절차
  templates/
    index.md
    feature-index.md
    spec.md
    design.md
    tasks.md
    validation.md
    decision.md
```

기능을 시작하면 `docs/specs/<번호>-<slug>/` 아래에 기능 인덱스와 필요한 문서를 생성한다. 아직 시작하지 않은 기능 폴더는 만들지 않는다.

## 탐색과 관리

- 기본 경로: `AGENTS.md → docs/index.md → 영역 index.md → 대상 문서`.
- 기능 작업은 대상 기능의 `index.md`와 `spec.md`를 읽고, 현재 단계에 필요한 문서만 추가로 읽는다.
- 문서 간 링크는 상대 경로를 사용한다. 인덱스에는 실제 존재하는 문서만 링크한다.
- 요구사항은 기능 명세, 공통 설계는 아키텍처, 결정 이유는 ADR에 기록한다. 중복 서술 대신 원문을 연결한다.
- 제품 범위와 확정 사항은 [프로젝트 인덱스](project/index.md)에서 확인한다. Windows·macOS·Linux에서 직접 실행하는 것을 목표로 하며 Codex와 자체 웹을 통해 사용하고 FastAPI에서 답변 생성 흐름을 처리한다. 지식 계층 설계와 기술 스택·운영체제 지원 기준은 [아키텍처 인덱스](architecture/index.md)에서 필요한 경우 읽는다.
