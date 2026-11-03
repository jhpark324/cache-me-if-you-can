# 리모트 등록 전 재점검 · README 보강

- 기준일: 2026-11-03
- 상태: 이번 재점검·README 보강 완료. 공개 라이선스·네이티브 OS·실계정 재로그인·원격 CI 관문은 별도.
- 요청: 리모트 업로드 전 최종 점검, 오픈 소스 프로젝트처럼 서비스 설명과 실제 화면을 갖춘 README 작성.
- 범위: 현재 코드·등록 후보·잠금 설치·테스트·CI 구성·문서·스크린샷. 원격 생성·push·공개 전환은 수행하지 않는다.
- 이전 근거: [2026-11-02 통합 점검](final-review.md), [유형·데이터 확장](record-kinds-and-scenarios.md), [출처 날짜](ui-ux-refinement.md).

## 수용 기준과 작업

- [x] 최신 백엔드·실제 CPU 임베딩 시험과 프런트 빌드·브라우저 회귀를 실행하고 실패를 확인한다.
- [x] 격리된 데이터로 실제 웹 API 경로를 검증한다. 현재 저장소·로그인을 보존한다.
- [x] 등록 후보에서 실행 DB·토큰·계정·로컬 경로·불필요한 산출물·라이선스 고지를 점검한다. 알려진 의존성 취약점 조회 범위를 기록한다.
- [x] README에 서비스 목적, 대표 화면, 사용 흐름, 설치·Codex 연결, 구조, 검증 범위와 미지원 사항을 실제 구현에 맞게 설명한다.
- [x] 새 화면은 합성 테스트 기록만 사용하며 날짜·버전·실행 결과를 꾸며내지 않는다. README 이미지·내부 링크·모바일 가독성을 확인한다.
- [x] 최신 결과와 남은 공개·OS·실계정 관문을 구분해 기록한다. 프로젝트 라이선스를 임의로 선택하지 않는다.

README는 모든 프로젝트 문서를 `docs/`에 둔다는 규칙에 따라 `docs/README.md`를 사용한다. [GitHub는 docs 디렉터리의 README도 자동 표시한다](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes). root나 `.github`에 중복 README를 만들어 내용이 갈라지게 하지 않는다.

## 검증 결과

**검증한 범위에서 새로운 차단 오류는 발견하지 않았다.** 이번 수정은 README·소개 이미지·문서의 현재 상태 정리이며 제품 동작과 잠금 버전은 바꾸지 않았다. 환경은 WSL Linux x64, Python 3.12, CPU, Node.js 22, Chromium이다.

| 검사 | 이번 결과 | 실제 범위 |
| --- | --- | --- |
| 백엔드 전체 | **260 passed / 0 skipped**, 43.42초 | 고정 KURE-v2 snapshot의 실제 CPU 임베딩 포함 |
| 웹 타입·빌드 | 성공 | TypeScript·Vite, 기존 큰 청크 경고는 아래에 구분 |
| 웹 회귀 | **74 passed / 3 skipped**, 2.4분 | 제외된 3개는 실제 HTTP 통합이며 다음 행에서 별도 실행 |
| 실제 HTTP 통합 | **3 passed**, 21.8초 | 새 임시 저장소에서 생성·정정·확인 삭제·그래프, 임시 서버 종료 확인 |
| 출처 날짜 | **6개 통과**, JS 오류·가로 넘침 0 | 현지 자정·과거 revision·분 단위 중복·누락/잘못된 값·320px. 이번 별도 검사이며 상시 회귀 파일 추가는 아님 |
| 스크립트 회귀 | **20 passed** | 등록 후보·실행기·대화 데이터의 기존 시험 |
| 테스트 데이터 | **40개 validate 성공** | README의 검증 명령 실행, 실제 기록 추가 없이 자료 구조 확인 |
| 프런트 깨끗한 설치 | `npm ci`·타입/빌드 성공 | 임시 폴더에 소스 28개만 복사, 기존 node_modules·dist 미사용, 원본/복사본 lock 변경 없음 |
| Python 환경 | 잠금 설치 상태 일치 | `uv sync --check --locked`로 109개 확인, 의존성 변경 없음 |
| wheel | offline 빌드·checkout 밖 실행 성공 | 패키지 내 migration·격리 API 확인. 기존 의존성을 재사용한 검사이며 새 기기 전체 설치 시험은 아님 |
| README 렌더 | 1280/390/320px 통과 | 이미지·Mermaid 정상, 가로 넘침·JS 오류 0, 상대 경로/앵커 25개 정상 |

근거: [종합 요약](artifacts/prepublish-2026-11-03/summary.json), [백엔드·wheel](artifacts/prepublish-2026-11-03/backend.json), [날짜 경계](artifacts/prepublish-2026-11-03/source-dates.json), [README 렌더](artifacts/prepublish-2026-11-03/readme-render.json). README 검사는 CommonMark·표·HTML과 GitHub 유사 CSS를 쓴 로컬 렌더이며 GitHub 호스팅 렌더 성공을 대신하지 않는다.

## README와 문서 변경

- [README](../../README.md)를 서비스 소개 → 사용 사례 → 실제 화면 → 저장·검색 흐름 → 기능 → 설치·Codex → 구조 → 데이터 범위 → 개발·라이선스 순서로 구성했다.
- 홈 그래프, 실제 검색 답변, 오른쪽 출처 패널, 모바일 화면의 **제품 캡처 4개**를 추가했다. 이미지 원본·촬영 범위는 [소개 자료 인덱스](../../assets/readme/index.md)에서 관리한다.
- 백업은 **내보내기만 구현**되었음을 코드와 대조해 명시했다. 가져오기·복원 화면을 제공한다고 설명하지 않는다.
- 소스 설치와 wheel 단독 설치를 구분하고, 테스트 데이터 저장 후 색인 준비를 기다린 다음 검증하도록 안내했다.
- 로컬 저장과 외부 AI 호출, 제한된 PII 처리, 현재 미구현 공유, soft delete의 내부 보존을 구분했다.
- [플랫폼 문서](../../architecture/platform-support.md)의 과거 패키지 표가 현재 의존성 버전 미고정을 뜻하는 것처럼 읽히던 문장을 정리했다. 현행 버전은 pyproject·lockfile을 기준으로 한다.
- 최종 점검·계획·탐색 인덱스를 이번 결과로 연결하고 과거 회차의 결과는 보존했다.

## 실제 화면과 사용자 상태

현재 저장소의 52개 제목이 모두 `[테스트]`인 합성 기록임을 먼저 확인하고, 기존 로그인·선택 모델로 “지우는 왜 복습 범위를 줄였어?”를 한 번 질문했다. **24.98초, 인용 출처 2개, 검색 청크 10개**를 관찰했다. 단일 질문 결과이며 응답 지연·품질의 일반 성능 지표는 아니다.

기록 ID/revision/상태, 로그인과 선택 모델을 전후 비교해 유지됨을 확인했다. 기록 변경 요청·브라우저 오류는 0건이다. 개인 계정 정보·설정 화면은 캡처하지 않았고, 데스크톱과 모바일 원본 4장을 직접 확인했다. [촬영 확인 결과](../../assets/readme/screenshots.json)

## 등록 후보·의존성·라이선스

[최종 preflight 결과](artifacts/prepublish-2026-11-03/preflight.json)의 알려진 비밀 패턴·민감 경로·대용량 파일·심볼릭 링크·Markdown 파일 링크 findings는 **0건**이다. `.git`이 아직 없으므로 임시 bare Git으로 ignore를 적용했고 저장소를 초기화하거나 stage하지 않았다. 사용자 DB·Lance 파일·토큰·환경 파일·가상환경·node_modules·실행 캐시·시험 결과가 등록 후보에서 제외되는지 확인했다. 새 스크린샷과 검증 요약은 합성/공개 가능한 내용만 포함한다.

| 의존성 조회 | 범위 | 알려진 취약점 |
| --- | --- | --- |
| [제품 npm](artifacts/prepublish-2026-11-03/npm-product.json) | 292개 의존성 | 0 |
| [프로토타입 npm](artifacts/prepublish-2026-11-03/npm-prototype.json) | 108개 의존성 | 0 |
| [보존한 그래프 vendor](artifacts/prepublish-2026-11-03/graph-vendor-advisories.json) | 고지된 36개 이름·버전을 npm 공식 advisory API로 별도 조회 | 0 |
| [Python](artifacts/prepublish-2026-11-03/python-public-packages.json) | pip-audit 2.10.1, 설치된 공개 패키지 107개 | 0 |
| [PyTorch](artifacts/prepublish-2026-11-03/torch-public-version.json) | 설치된 `2.15.0+cpu` 대신 공개 기준 `2.15.0` 별도 조회 | 0 |

자체 프로젝트 `second-brain 0.1.0`은 공개 취약점 조회 대상에서 제외했다. PyTorch CPU 빌드·보존된 JS 번들의 바이너리/공급망 검증이나 알려지지 않은 취약점 인증으로 해석하지 않는다. 잠금 파일 3개는 변경하지 않았다.

보존한 그래프 번들 36개 구성요소의 고지와 복사본 일치, 프로토타입 UI production 의존성 81개와 고지 81행의 이름·버전 일치, Pretendard·SUIT의 OFL/저작권 고지 및 실제 폰트의 고지를 확인했다. **프로젝트 자체 라이선스는 미정**이며 임의로 추가하지 않았다.

검사는 현재 등록 후보와 알려진 패턴을 다룬다. 존재하지 않는 Git 과거 이력, 모든 형식의 비밀, 외부 URL 전체, 모든 바이너리·이미지에 대한 자동 비밀 탐지까지 수행한 것은 아니다. CI의 읽기 권한·commit SHA 고정·인증 미보존·잠금 설치를 확인했으나 호스팅 실행은 남아 있다.

## 남은 결정과 후속 작업

| 항목 | 이번 판단 |
| --- | --- |
| 프로젝트 라이선스·원격 공개 범위 | 저작권자의 결정 필요. 코드 보관과 공개 재배포의 조건을 구분한다. |
| GitHub CI | remote 생성·push 뒤 첫 실행을 확인해야 한다. 이번에는 수행하지 않았다. |
| 네이티브 OS·브라우저 | Windows/macOS/Linux 전체 조합 미검증. Intel Mac·Windows ARM 패키지 제약을 유지하며 WSL/Chromium 결과로 지원 완료를 선언하지 않는다. |
| 실계정 로그아웃→재로그인 | 사용자의 보류를 유지한다. 현재 로그인 보존과 실제 답변 성공만 확인했다. |
| 배포 패키징 | wheel에는 웹 빌드가 없어 README의 소스 설치가 현재 지원 경로다. 독립 배포는 후속 작업이다. |
| 성능·유지보수 | graph 청크 약 1,419kB(gzip 378kB), 메인 534kB(gzip 163kB), CSS 728kB(gzip 92kB). 대규모 검색·깊은 출처·자동 주제 분류 품질과 함께 후속 평가한다. |

현 단계의 원격 등록 전 점검은 완료했다. 미검증 관문 때문에 004 전체 상태는 `in-progress`를 유지한다. 사용자 데이터·인증을 변경하거나 원격 저장소 생성·push·공개 배포를 수행하지 않았다.
