# Astryx 프런트엔드 작업 가이드

`frontend/`의 UI·레이아웃·테마 작업에 적용한다. Astryx core·theme-neutral·CLI는 같은 `0.7.16` 버전을 사용하고 실제 의존성은 [웹 패키지](../../frontend/package.json)와 lockfile을 따른다. 아래 관리 지침은 `astryx init`이 생성한 프런트엔드 에이전트 안내를 이 프로젝트의 문서 위치 규칙에 맞춰 옮긴 것이다. Gemini용 안내도 같은 내용을 참조하므로 별도 중복 파일을 두지 않는다.

## 캐시미 화면에 적용하는 기준

기존 화면의 한국어 문구, 기록·검색·설정 흐름과 키보드 동작을 보존하며 Astryx 구성요소로 교체한다. 화면을 처음부터 다시 만들지 않으므로 기존 페이지 예외를 적용한다. [웹 명세](../specs/workspace.md)가 제품 동작의 기준이다.

| 영역 | 적용 |
| --- | --- |
| 색과 대비 | 어두운 중립색 표면을 유지한다. 따뜻한 포인트 색은 주 작업과 현재 선택을 구분하는 데 절제해 사용한다. 팔레트는 테마에서 설정한다. |
| 글꼴 | 한국어 본문과 UI는 기존 Pretendard를 유지하고 Astryx 테마의 글꼴·타입 토큰에 연결한다. |
| 실행·입력 | 액션은 Button·IconButton, 지원하는 입력은 Astryx 입력 구성요소를 사용한다. 네이티브 월 입력 등 제공되지 않는 동작은 기존 HTML 의미와 이벤트를 보존하고 테마 토큰을 사용한다. |
| 제목·본문 | DialogHeader·Heading·Text로 문서 계층과 포커스·접근성 이름을 보존한다. |
| 기록·목록 | 카드 반복 대신 행 구조를 유지한다. 레이아웃과 간격은 Stack·Layout 계열의 props와 토큰을 사용한다. |
| 스타일 진입점 | reset·Astryx 스타일과 앱 스타일은 [main.tsx](../../frontend/src/main.tsx)에서 중앙 관리한다. 화면별 파일에서 스타일을 중복 로드하지 않는다. |

테마를 바꾼 뒤에는 생성된 테마 미리보기와 실제 화면을 확인한다. `astryx init`을 다시 실행해 안내가 갱신되면 변경된 지침을 이 문서에 반영하고 프런트엔드에 중복 문서를 남기지 않는다.

## 제품 테마 수정과 생성

색·글꼴의 원본은 [cacheMeTheme.ts](../../frontend/src/theme/cacheMeTheme.ts)이며 Astryx neutral 테마를 확장한다. 원본을 수정한 뒤 `frontend/`에서 `npm run theme:build`를 실행해 `src/theme/cache-me.css`, `cache-me.js`와 타입 선언 파일을 함께 갱신한다. 생성 파일은 직접 수정하지 않고 원본과 함께 커밋한다. 앱은 [main.tsx](../../frontend/src/main.tsx)에서 생성된 테마 모듈과 CSS를 불러와 다크 모드로 적용한다.

`npm run theme:check`는 파일을 변경하지 않고 원본과 생성 결과가 일치하는지 확인한다. `npm run build`도 이 검사를 먼저 실행하므로, 테마를 바꾼 뒤 생성 파일을 갱신하지 않으면 빌드가 실패한다.

## Astryx 관리 지침

다음은 설치기가 생성한 지침이다. 명령은 `frontend/`에서 실행한다.

<!-- ASTRYX:START -->
Astryx v0.7.16 · 174 components
CLI: run every command as `npx astryx <cmd>` (shown below as `astryx ...`).

SETUP (once, in app entry e.g. main.tsx) — without these, components render unstyled:
  import "@astryxdesign/core/reset.css";
  import "@astryxdesign/core/astryx.css";

WORKFLOW — start every page from a template, never from scratch:
1. `astryx build "<idea>"` — names the template to scaffold from and the parts it lacks.
2. `astryx template <name> <path>` — scaffold it; keep its frame, gap and padding; replace the content.
3. `astryx template <Block>` for parts it lacks; `astryx component <Name>` to read props before using one.
Changing an existing page? Keep it: skip step 2 and add blocks/components inside its sections.
Before you deliver a build, run `astryx doctor --built <dir>`; don't deliver it if it fails.

RULES:
- No <div> — components handle all layout and spacing.
- Read `astryx docs layout` before changing a template's frame.
- Dense data = rows (Table, List/Item), not Card-wrapped lists. Badge = counts only.
- Style with component props first, then tokens (var(--color-*|--spacing-*|--radius-*)). No raw hex/px. No StyleX/Tailwind compiler here — don't use xstyle/utility classes directly. Some templates use StyleX and need a compiler plugin; see `astryx docs styling-overview`.
- THEMES: palettes and custom colors go through the theme, never :root overrides. To make or change a theme (colors, fonts, corners, spacing, a look from a picture), prefer the experimental theme editor over hand-written theme files: `astryx experimental theme editor new <name> --like neutral`, then `editor set <name> <thing> <value>` or `editor how "<what you want>"`; wire it with `astryx theme add <name>`; after each change look at it with `astryx experimental theme editor show <name> --png` and open the PNGs it writes (changes nothing in the app); a theme change is not done until you have looked at the pictures. In code, extend an imported theme to customize it; `theme eject <slug>` only forks source. See `astryx docs theme`.
- SELF-CHECK: re-read the file; replace any raw <div>/<span>, imported .css/@apply, or hardcoded #hex/px with the component or a token.

`astryx help` lists every command. Key ones beyond the workflow:
  search "<query>"   find any component / hook / doc / template
  discover <words>   integrations you could add
  docs <topic>       getting-started, principles, tokens, theme … (`astryx docs` lists all)
  docs cli           commands and API reference
  docs authoring     build an integration package, and every field it holds
  upgrade --from <old version> --apply   run after a dependency bump
<!-- ASTRYX:END -->
