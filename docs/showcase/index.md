# 프로젝트 소개 사이트

[배포된 소개 페이지](https://jhpark324.github.io/cache-me-if-you-can/)는 발표·전시에서 QR로 접속하는 관람객용이다. [화면](index.html), [스타일](styles.css), [시연 선택](script.js), [인쇄용 QR](media/intro-qr.png)을 이 폴더에서 관리한다. GitHub 링크는 상단에 있고, 영상과 구조 설명은 같은 페이지에서 볼 수 있다.

첫 화면은 TCP·UDP 예시 대화에서 시작한다. 대화에서 TCP 설명을 듣고 UDP도 물어본 다음 저장을 요청한다. 다음·이전 버튼으로 대화 → 기록 두 건 → 그래프의 세부 항목 → 지식 공간 검색과 근거 → 비교 아티클을 따라간다. 이야기 속 짧은 GIF는 활성 장면에서만 불러오고, 정지하거나 모션 감소 설정에서 정적 사진으로 볼 수 있다.

| 상세 시연 | 노트북 전체 화면에서 보는 장면 |
| --- | --- |
| [기록 저장](media/records.mp4) | TCP·UDP 내용이 서로 다른 기록으로 저장된 결과를 열어 본다. |
| [그래프 탐색](media/graph.mp4) | ‘전송 계층’에 연결된 기록에서 UDP의 세부 항목을 골라 원문 구간과 전체 기록을 읽는다. |
| [지식 공간 검색](media/search.mp4) | 음성 조각 손실을 질문하고 답변에서 인용한 UDP 구간과 검색 중에 읽은 TCP 구간을 확인한다. |
| [아티클 읽기](media/article.mp4) | 두 기록으로 발행한 비교표를 읽고 같은 자리에서 TCP와 UDP의 출처를 확인한다. |

영상은 격리 서재의 합성 기록을 1440×810으로 촬영하고 대기를 편집했다. 검색 시연은 격리된 서재에서 실제 색인·검색·원문 검증을 실행하고, 외부 모델 응답은 재현 가능한 예시로 제공한다. 모바일에서도 같은 프레임을 보며 한국어 자막과 전체 화면 재생을 사용할 수 있다.

[발표 자료](https://jhpark324.github.io/cache-me-if-you-can/#presentation)에서는 면접 전날 TCP·UDP 공부 기록을 다시 찾는 이야기를 17장으로 읽는다. 같은 섹션에서 PDF를 열거나 내려받을 수 있다. 배포할 때는 [발표 원본](../assets/index.md)의 HTML과 PDF를 함께 복사한다.

## 설계 문서

[아키텍처 개요](guide.html)에서 시스템 지도를 보고, 각 장에서 해당 알고리즘과 사례를 확인한다. 그림은 편집 가능한 Excalidraw 장면에서 내보낸 SVG로 게재한다.

| 설계 주제 | 해설 | Excalidraw 원본 |
| --- | --- | --- |
| 웹·MCP 진입점, 공통 서비스와 저장소 경계 | [시스템 아키텍처](guide-system.html) | [시스템 구성](media/diagrams/system-routes.excalidraw) |
| 기록과 아티클의 작성·저장 책임 | [Codex 스킬 동작 명세](guide-skills.html) · [MCP 도구 명세](guide-mcp.html) | [스킬 실행](media/diagrams/skill-to-library.excalidraw) |
| 주제 후보 선별, 기존 주제 재사용·신규 생성·보류 | [주제 매칭과 등록](guide-topics.html) | [저장 후 주제 연결](media/diagrams/topic-assignment.excalidraw) |
| 키워드·벡터·주제 검색과 출처 검증 | [저장·검색 엔진과 RRF](guide-engine.html) | [검색과 인용](media/diagrams/retrieval-evidence.excalidraw) |

[제품 기능](guide-features.html)에서는 그래프의 세부 항목과 답변의 근거를 따라가 볼 수 있다. [원문 자료집](guide-library.html)은 기능 명세, 시스템 설계, 기술 결정을 분야별로 모은다. [자료집 생성기](../../frontend/scripts/render-showcase-reference.mjs)가 저장소의 Markdown에서 원문과 검색 색인을 만들고, [문서 탐색 생성기](../../frontend/scripts/showcase-navigation.mjs)가 각 문서에 같은 목차와 현재 위치를 표시한다.

MCP 페이지의 [스키마](contracts/mcp-schemas.json)는 등록된 도구의 입력과 반환 계약을 담는다. [호출 예시](contracts/mcp-examples.json)는 빈 테스트 서재에서 기록을 저장하고, 원문을 조회한 뒤 아티클을 발행한 결과다. 도구 계약을 바꿀 때는 [생성기](../../backend/scripts/export_mcp_guide.py)로 스냅샷을 갱신한다. [백엔드 검사](../../backend/tests/test_showcase_mcp_contract.py)가 실제 서버의 스키마 및 예시와 대조한다. 저장소 루트에서 다음 명령으로 같은 검사를 실행할 수 있다. 스냅샷을 갱신할 때는 `--check`를 생략한다.

```sh
uv run --project backend python backend/scripts/export_mcp_guide.py --check
```

## GitHub Pages 배포

[GitHub Actions](../../.github/workflows/pages.yml)는 [패키징 스크립트](../../scripts/build_showcase.py)로 소개 페이지와 미디어를 빌드한다. [정적 렌더러](../../frontend/scripts/render-showcase.mjs)는 HTML의 `data-ax` 표시를 [프런트엔드가 사용하는 Astryx](../guides/astryx.md)의 제목·본문·버튼·레이아웃 컴포넌트로 렌더링한다. 배포본에는 필요한 CSS와 [Astryx 라이선스 고지](licenses/astryx.txt)가 함께 들어간다. 변경 PR에서는 패키징을 검증하고 `main`에 반영되면 GitHub Pages에 배포한다.

로컬 미리보기에는 Node.js와 Python이 필요하다. 저장소 루트에서 다음 명령을 실행한 뒤 `http://127.0.0.1:8000`을 연다. 동작 기준은 [소개 사이트 명세](../specs/showcase.md)에 있다.

```sh
npm --prefix frontend ci
showcase_preview="$(mktemp -d)/site"
python3 scripts/build_showcase.py "$showcase_preview"
frontend/node_modules/.bin/vite preview --outDir "$showcase_preview" --host 127.0.0.1 --port 8000 --strictPort
```
