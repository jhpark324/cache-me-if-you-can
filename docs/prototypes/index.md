# 디자인 프로토타입

제품 구현 전 디자인과 상호작용을 검토하는 산출물을 관리한다. 목데이터 화면이 실제 저장소·모델·검색 기능을 제공한다는 의미는 아니다.

| 시안 | 상태 | 관련 문서 |
| --- | --- | --- |
| [검정 배경 지식 탐색](knowledge-space/index.html) | `verified` — 흰색 본문·주황 강조·어두운 유리 팔레트 | [003 명세](../specs/003-knowledge-space-design/index.md), [제품 맥락](knowledge-space/PRODUCT.md), [디자인 기준](knowledge-space/DESIGN.md), [UI 라이브러리 선정](knowledge-space/ui-library-selection.md) |

## 실행

[로컬 프리뷰](http://127.0.0.1:4381/?v=5)에서 최신 시안을 확인한다. `http://localhost:4381/`도 같은 서버를 가리킨다. 서버가 종료된 경우 프로젝트 환경에서 다음 명령으로 다시 실행한다.

개정판의 React 소스나 라이브러리를 변경한 경우 먼저 다음 경로에서 정적 번들을 다시 만든다. 설치 버전은 해당 경로의 lockfile을 따른다.

```bash
cd docs/prototypes/knowledge-space
npm ci
npm run build
```

```bash
python3 -m http.server 4381 --bind 127.0.0.1 --directory .
```

이 프리뷰는 정적 목데이터 화면이다. 공개 배포·로그인·실제 기록 저장소 또는 모델 연결을 수행하지 않는다. 2026-11-02 이전 v4 HTML과 SUIT 폰트가 Windows `Invoke-WebRequest`에서 HTTP 200을 반환했고 WSL 브라우저 검증을 수행했다. 새 팔레트는 별도로 확인한다.

## 확인 근거와 자산

| 자료 | 내용 |
| --- | --- |
| [검증 기록](../specs/003-knowledge-space-design/validation.md) · [검사 결과 JSON](knowledge-space/validation-results.json) | v5 색상·명암·세 크기 캡처 확인. v4 기능 검사 50개는 별도 기준으로 보존 |
| [데스크톱 그래프](knowledge-space/screenshots/desktop.png) · [검색 답변](knowledge-space/screenshots/desktop-answer.png) · [출처 패널](knowledge-space/screenshots/desktop-source.png) | 최신 v5의 1440 × 1000 화면 |
| [모바일 그래프](knowledge-space/screenshots/mobile.png) · [검색 답변](knowledge-space/screenshots/mobile-answer.png) · [출처 패널](knowledge-space/screenshots/mobile-source.png) | 최신 v5의 390 × 844 화면 |
| [태블릿 출처 패널](knowledge-space/screenshots/tablet-source.png) | 최신 v5의 1024 × 768 화면 |
| [자산 출처](knowledge-space/assets/index.md) | 로컬 글꼴과 배포 라이선스 |
| [그래프 라이브러리 라이선스](knowledge-space/vendor/THIRD-PARTY-LICENSES.md) | 재사용한 라이브러리와 종속성의 라이선스 원문 |
| [UI 라이브러리 라이선스](knowledge-space/vendor/UI-LICENSES.md) | React·React DOM·Radix Themes·Lucide 및 production 의존성의 라이선스 원문 |

기존 001 시안은 폐기된 디자인 이력이며 이 목록의 활성 디자인 기준이 아니다. 기존 채택 그래프 라이브러리의 재사용은 이전 시안의 화면 구성을 다시 채택하는 것을 뜻하지 않는다.
