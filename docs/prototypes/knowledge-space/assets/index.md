# 디자인 프리뷰 자산

폰트는 실행 중 외부 요청 없이 이 폴더에서 제공한다.

| 자산 | 출처·버전 | 라이선스·용도 |
| --- | --- | --- |
| [SUIT-Variable.woff2](SUIT-Variable.woff2) | [공식 저장소 v2.0.5](https://github.com/sun-typeface/SUIT/tree/v2.0.5), 커밋 `55118d981336d8fce005eb62888c12c0568ef7b0`의 `fonts/variable/woff2/SUIT-Variable.woff2` | [SIL OFL 1.1 원문](SUIT-OFL.txt). 검색·답변·좌우 패널의 UI 본문에 적용 |
| [PretendardVariable.woff2](PretendardVariable.woff2) | [Pretendard 1.3.9 원본](https://github.com/orioncactus/pretendard) | [SIL OFL 1.1 원문](OFL.txt). SUIT에 없는 문자용 로컬 대체 폰트 |

## SUIT 적용 기준

- 제작자는 SUIT를 UI 본문용으로 소개하며, 한글에 맞춘 영문·숫자와 가변 굵기를 제공한다. [공식 소개](https://sun.fo/suit/)
- CSS 패밀리명은 `SUIT Variable`, 정상 스타일의 가변 굵기 범위는 `100 900`이다. `@font-face`에서 로컬 파일과 `format('woff2')`를 지정한다. 범위는 [공식 CSS](https://github.com/sun-typeface/SUIT/blob/v2.0.5/fonts/variable/woff2/SUIT-Variable.css)로 확인했다.
- 이번 시안에서의 선택 근거는 한글·영문·숫자가 섞인 짧은 UI 문구의 형태를 맞추고 굵기를 세밀하게 조절하기 위한 것이다. 폰트 교체만으로 가독성이 개선된다는 검증 결과는 아니다.
- 본문·주요 탐색 항목은 15–16px를 검토 시작점으로 삼고, 본문 400–500·조작 요소 500–600을 중심으로 크기·행간·명암을 함께 확인한다. 작은 글자에 과도한 음수 자간이나 흐린 회색을 적용하지 않는다.
- 공식 소개에 따르면 한글 범위를 선별해 담고 있으므로, 사용자 기록에 드문 음절이 들어오는 경우를 위해 기존 로컬 Pretendard와 시스템 폰트를 대체 목록에 유지한다.

2026-11-02 내려받은 파일은 수정하지 않았다. WOFF2 시그니처·파일 길이 일치와 `file`의 TrueType 기반 WOFF2 인식을 확인했고, `fc-scan`으로 `SUIT Variable` 패밀리와 가변 폰트 및 9개 명명 굵기를 확인했다. 파일 크기는 624,536 bytes이며 SHA-256은 `aa894a204d5a6fbae259dac6868d350cbd373a390caee0313f92946af741df23`이다. 라이선스 원문의 저작권과 Reserved Font Name `SUIT` 표기를 그대로 보존했다.

그래프 라이브러리와 라이선스는 별도 `../vendor/`에 보관하며 폐기한 시안의 그래픽 디자인을 복사하지 않았다.
