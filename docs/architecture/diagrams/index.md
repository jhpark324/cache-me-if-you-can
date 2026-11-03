# 아키텍처 다이어그램

[전체 보기](../overview.html)에서 도식과 원문을 함께 탐색한다. 각 문서의 Mermaid가 수정 원본이며 아래 SVG는 렌더링 결과다. 구현·수정 완료와 제안을 구분한다.

| 도식 | 상태 | 수정 원본 |
| --- | --- | --- |
| [시스템과 신뢰 경계](current-system-rendered-1.svg) | 구현 | [원문](../../architecture/current-system.md) |
| [실행 모듈](current-system-rendered-2.svg) | 구현 | [원문](../../architecture/current-system.md) |
| [정본 데이터 관계](current-system-rendered-3.svg) | 구현 | [원문](../../architecture/current-system.md) |
| [배포와 실행 데이터](current-system-rendered-4.svg) | 구현 | [원문](../../architecture/current-system.md) |
| [저장과 비동기 처리](runtime-flows-rendered-1.svg) | 구현 | [원문](../../architecture/runtime-flows.md) |
| [단일 질문과 답변](runtime-flows-rendered-2.svg) | 구현 | [원문](../../architecture/runtime-flows.md) |
| [수정과 출처 자격](runtime-flows-rendered-3.svg) | 구현 | [원문](../../architecture/runtime-flows.md) |
| [삭제 확인과 동시성](runtime-flows-rendered-4.svg) | 구현 | [원문](../../architecture/runtime-flows.md) |
| [로그인과 취소](runtime-flows-rendered-5.svg) | 구현 | [원문](../../architecture/runtime-flows.md) |
| [리팩토링 순서](maintenance-review-rendered-1.svg) | 개선 방향 | [원문](../../architecture/maintenance-review.md) |
| [차별화 기능의 연결](evolution-proposals-rendered-1.svg) | 제품 제안 | [원문](../../project/evolution-proposals.md) |
| [로컬 저장과 외부 추론](second-brain-comparison-2026-11-rendered-1.svg) | 구현·조사 | [원문](../../research/second-brain-comparison-2026-11.md) |
| [공통 필터 의미](backend-final-review-rendered-1.svg) | 수정 완료 | [원문](../../specs/004-local-runtime/backend-final-review.md) |
| [웹 컴포넌트 경계](frontend-final-review-rendered-1.svg) | 수정 완료 | [원문](../../specs/004-local-runtime/frontend-final-review.md) |

## 다시 생성

Mermaid CLI를 별도 도구 환경에 설치한 뒤 프로젝트 루트에서 실행한다. 제품 의존성에는 포함하지 않는다. 이 회차는 CLI 12.0.0과 Chromium으로 렌더링했다. 브라우저·한글 글꼴과 OS 실행 의존성이 필요하다.

```sh
python scripts/render_diagrams.py --mermaid-cli <mmdc 실행 경로>
```

필요하면 `--puppeteer-config`로 Chromium 경로와 실행 인자를, `--mermaid-config`로 테마·글꼴을 지정한다. SVG가 이미 있으면 인자 없이 HTML과 인덱스만 다시 생성한다. 문서에 도식을 추가하면 스크립트의 목록·제목도 갱신한다.
