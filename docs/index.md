# Cache Me If You Can 문서

처음 사용한다면 [제품 소개](README.md)에서 시작한다. 설치·실행은 [로컬 가이드](guides/local-development.md), 기여를 위한 구조와 검사는 [현재 시스템](architecture/current-system.md)과 [검사 가이드](guides/testing.md)를 따른다.

| 목적 | 진입 문서 |
| --- | --- |
| 제품 기능과 범위 이해 | [제품](project/index.md) |
| 발표·전시용 소개와 기능 시연, 기능·시스템 심화 가이드 | [프로젝트 소개 사이트](showcase/index.md) |
| 도메인 용어와 코드 대응 확인 | [도메인 용어](project/domain-language.md) |
| 설치·설정·문제 해결 | [로컬 실행](guides/local-development.md) |
| Codex에서 기록 관리·아티클 작성 | [스킬](skills/index.md) |
| 합성 예제 사용 | [예제](examples/index.md) |
| 기능을 변경하기 전 계약 확인 | [현재 기능 명세](specs/index.md) |
| 저장·검색·AI·화면 구조 이해 | [아키텍처](architecture/index.md) |
| 기술 선택의 이유 확인 | [설계 결정](decisions/index.md) |
| 개발·검사·PR·배포 준비 | [기여 가이드](guides/index.md) |
| 기술 조사와 평가 | [연구](research/index.md) |
| 소개용 이미지 | [자산](assets/index.md) |
| 새 명세·ADR 작성 | [문서 템플릿](templates/index.md) |

## 문서 탐색

작업에 해당하는 인덱스에서 필요한 문서만 읽는다. 링크가 있다는 이유로 전체 문서 트리를 재귀적으로 읽지 않는다. 작업 범위가 넓어질 때 관련 문서를 추가로 확인한다.

현재 요구사항은 `specs/`, 공통 구조·계약은 `architecture/`, 기술 선택의 이유는 `decisions/`에서 관리한다. 문서를 생성·이동·제거하면 가장 가까운 `index.md`와 참조를 갱신한다. 공개 문서의 범위와 일회성 실행 결과의 보관은 [문서 관리 원칙](guides/documentation.md)을 따른다.
