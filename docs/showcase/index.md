# 프로젝트 소개 사이트

[배포된 소개 페이지](https://jhpark324.github.io/cache-me-if-you-can/)는 발표·전시에서 QR로 접속하는 관람객용이다. [화면](index.html), [스타일](styles.css), [시연 선택](script.js), [인쇄용 QR](media/intro-qr.png)을 이 폴더에서 관리한다. GitHub 링크는 상단에 있고, 영상과 구조 설명은 같은 페이지에서 볼 수 있다.

| 시연 | 실제 화면에서 확인하는 동작 |
| --- | --- |
| [결정의 출처](media/recall.mp4) | 결정 기록에서 인용 당시 문장을 열고 최신 버전과 대조한다. |
| [기록 남기기](media/records.mp4) | 웹에서 기록을 작성한 뒤 타임라인에서 저장본을 다시 연다. |
| [그래프 탐색](media/graph.mp4) | 주제를 선택하고 연결된 기록의 본문을 찾는다. |
| [아티클 읽기](media/article.mp4) | MCP 등록 결과를 확인하고 웹의 차트와 출처 패널을 읽는다. |

영상에는 격리한 서재와 합성 기록을 사용했다. 재생 시간을 줄이기 위해 대기 구간을 편집했으며 한국어 WebVTT 자막과 대표 프레임을 함께 배포한다.

[GitHub Actions](../../.github/workflows/pages.yml)는 [패키징 스크립트](../../scripts/build_showcase.py)로 소개 페이지와 미디어를 빌드한다. [정적 렌더러](../../frontend/scripts/render-showcase.mjs)는 HTML의 `data-ax` 표시를 [프런트엔드가 사용하는 Astryx](../guides/astryx.md)의 제목·본문·버튼·레이아웃 컴포넌트로 렌더링한다. 배포본에는 필요한 CSS와 [Astryx 라이선스 고지](licenses/astryx.txt)가 함께 들어간다. 변경 PR에서는 패키징을 검증하고 `main`에 반영되면 GitHub Pages에 배포한다.

로컬 미리보기에서는 저장소 루트에서 다음 명령을 실행한 뒤 `http://127.0.0.1:8000`을 연다. 동작 기준은 [소개 사이트 명세](../specs/showcase.md)에 있다.

```sh
npm --prefix frontend ci
showcase_preview="$(mktemp -d)/site"
python3 scripts/build_showcase.py "$showcase_preview"
python3 -m http.server --bind 127.0.0.1 --directory "$showcase_preview" 8000
```
