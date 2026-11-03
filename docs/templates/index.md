# 문서 템플릿 인덱스

문서를 생성할 때 해당 템플릿만 읽는다. 이 폴더는 양식이며 실제 기능 명세나 결정 기록이 아니다.

| 템플릿 | 생성 위치 | 용도 |
| --- | --- | --- |
| [기능 인덱스](feature-index.md) | `docs/specs/<slug>/index.md` | 기능 상태와 문서 탐색 |
| [명세](spec.md) | `docs/specs/<slug>/spec.md` | 문제·범위·수용 기준 |
| [설계](design.md) | `docs/specs/<slug>/design.md` | 구현 방식과 영향 범위 |
| [작업](tasks.md) | `docs/specs/<slug>/tasks.md` | 구현 작업과 진행 상태 |
| [검증](validation.md) | `docs/specs/<slug>/validation.md` | 수용 기준별 결과와 근거 |
| [결정 기록](decision.md) | `docs/decisions/ADR-<세 자리 번호>-<kebab-case 이름>.md` | 선택의 배경·대안·결과 |

복사 후 자리표시자를 실제 내용으로 바꾸고, 필요 없는 항목과 생성하지 않은 문서 링크를 제거한다. 생성한 문서는 소속 인덱스에 등록한다. 파일명 변경이나 이동으로 상대 링크가 달라지면 함께 수정한다.
