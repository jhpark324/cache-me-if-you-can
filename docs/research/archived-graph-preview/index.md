# 보관한 3D 그래프 실험 — 디자인 시안 폐기

- 처리일: 2026-11-02
- 상태: 과거 기술 실험 이력만 보관; 현재 디자인 참고 대상 아님
- 결정: [ADR-004 — 3D 그래프 라이브러리 채택](../../decisions/ADR-004-graph-visualization-library.md)

사용자는 `3d-force-graph` + Three.js + `three-spritetext`를 채택하고 세부 디자인은 별도로 진행하기로 했다. 이 폴더의 화면·색상·타이포그래피·패널 배치·노드 모양·샘플 문구는 폐기한 시안이며 새 디자인과 제품 화면 코드의 기준으로 사용하지 않는다. 아래 자료는 버전 호환성·과거 조작 검증 이력을 확인할 때만 읽는다.

## 기술 근거

검증한 시작 조합은 `3d-force-graph` 1.80.1, `three` 0.180.0, `three-spritetext` 1.10.0이다. 당시 Chromium·SwiftShader에서 작은 합성 그래프를 검증했다. Three.js 0.187.0 조합의 pointerup 오류를 확인하고 0.180.0 조합을 재검증한 경위를 보존한다. 실제 제품·전체 OS·대규모 성능 검증은 별도다.

## 보관 자료

| 자료 | 보존 목적 |
| --- | --- |
| [과거 실험 명세](spec.md) | 당시 테스트 범위; 제품 요구사항으로 승계하지 않음 |
| [과거 검증 기록](validation.md) / [원시 결과](validation-results.json) | 실행 환경·조작 결과·제약·해시 |
| [패키지 목록](package.json) / [lockfile](package-lock.json) | 당시 버전 조합과 번들 빌드 재현 |
| [라이선스](vendor/THIRD-PARTY-LICENSES.md) | 포함한 오픈소스의 표시 유지 |
| [과거 제품 맥락](historical-product-context.md) | 폐기한 화면을 만들 당시의 가정 |
| [과거 실험 화면](preview.html) | 기술 재현용 보관본; 디자인 참고 금지 |
| [화면 코드](app.js) / [스타일](styles.css) / [목데이터](mock-data.js) / [번들 진입점](vendor-entry.js) | 기존 검증 해시와 기술 이력 보존; 제품 UI로 복사하지 않음 |
| [데스크톱](screenshots/desktop.png) / [상세](screenshots/desktop-detail.png) / [모바일](screenshots/mobile.png) / [모바일 상세](screenshots/mobile-detail.png) | 과거 검증 캡처; 현재 디자인 기준 아님 |

실험을 재현해야 할 경우에만 이 폴더에서 `python3 -m http.server 4381 --bind 127.0.0.1`로 실행한다. 번들 재생성 명령은 `npm ci && npm run build:vendor`이며, 재생성하면 기존 원시 결과의 파일 해시와 달라질 수 있다. 운영 화면이나 개발 기본 실행 경로로 사용하지 않는다.

이 자료는 기존 `docs/specs/001-knowledge-graph-preview/`에서 옮겼다. 런타임 코드·번들·목데이터·스크린샷은 과거 검증 증거를 위해 그대로 유지했고 문서의 폐기 상태와 탐색 경로만 갱신했다.
