# 리모트 등록 전 확인과 재현

로컬 사전 점검 결과는 [2026-11-03 재점검](../specs/004-local-runtime/prepublish-review-2026-11-03.md)이 기준이다. 이 문서는 같은 검사를 다시 실행하는 방법이다. 사전 점검은 원격 등록 이전 시점의 기록이며, 이후 사용자 요청에 따라 아래 비공개 원격 저장소를 만들었다.

## 비공개 원격 저장소

- 저장소: [jhpark324/cache-me-if-you-can](https://github.com/jhpark324/cache-me-if-you-can)
- 생성일: 2026-11-03, 사용자 요청에 따른 개인 계정의 일반 비공개 저장소. fork·template가 아니다.
- 작업 브랜치: `main`, 원격 이름: `origin`.
- 프로젝트 라이선스는 미정으로 유지한다. 비공개 코드 보관 요청을 공개 재배포 승인으로 해석하지 않는다.
- [GitHub Actions](https://github.com/jhpark324/cache-me-if-you-can/actions)는 push마다 실행한다. 특정 커밋의 실행 결과는 해당 run에서 확인한다.

## 등록 후보 검사

프로젝트 루트에서 Git과 Python으로 실행한다.

```sh
python scripts/preflight.py
python -m unittest discover -s scripts/tests -v
```

Git이 아직 초기화되지 않았어도 임시 bare Git 디렉터리로 `.gitignore`를 적용한다. 작업 폴더에 `.git`을 만들거나 파일을 stage하지 않는다. 초기화된 저장소에서는 추적 중인 작업 파일과 현재 Git index의 blob을 모두 검사한다. 뒤늦게 `.gitignore`에 넣거나 작업 파일만 정리하고 stage한 비밀은 남겨둔 경우도 검사한다. Git 이력을 훑거나 index를 바꾸지는 않는다.

검사 대상은 현재 등록 후보 파일의 위험 경로, 일부 알려진 비밀 패턴, 10MiB 초과 파일, 심볼릭 링크와 Markdown 상대 링크다. 출력은 파일·규칙·행 번호만 포함하며 비밀 값을 출력하지 않는다. 이 검사는 Git 과거 이력·원격 설정·이미지 속 글자·임의 형식의 모든 비밀을 검사하는 도구는 아니다. 새 스크린샷·내보내기 파일은 내용도 확인해야 한다.

`.gitignore`는 가상환경·node_modules·실행 DB·Lance 파일·인증 JSON·환경 파일·개인 캐시·브라우저 시험 부산물을 제외한다. 잠금 파일은 포함한다. 보존한 프로토타입의 정적 번들·라이선스·합성 자료 캡처와 개인정보 경로를 제거한 조사 로그 2개는 문서 근거로 의도적으로 포함한다. `docs/`에 있다고 해서 실제 사용자 백업·인증 파일을 넣어도 된다는 뜻은 아니다.

## 잠금 설치와 검사

```sh
python scripts/manage.py setup
python scripts/manage.py check
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend test
```

`manage.py`의 uv 명령은 `--locked`, 프런트는 `npm ci`를 사용한다. `check`는 등록 후보·스크립트 회귀·백엔드 시험·웹 타입/빌드를 실행한다. 브라우저 시험은 마지막 두 명령으로 별도 실행한다. Linux에서 브라우저 OS 라이브러리가 없으면 Playwright의 `install --with-deps chromium` 경로가 필요하다.

실제 CPU 모델 시험은 `KURE_TEST_MODEL_PATH`에 [고정 snapshot](local-development.md#실행-설정)을 지정해야 한다. 미지정은 1개 skip이며 모델 시험 성공으로 기록하지 않는다. 실제 HTTP 통합은 격리된 데이터 디렉터리의 서버에만 `SECOND_BRAIN_TEST_URL`과 `SECOND_BRAIN_INTEGRATION=1`을 지정한다. 이 시험은 기록 생성·정정·확인 삭제를 하므로 사용 중인 8000 저장소를 지정하지 않는다.

## CI 범위

[워크플로](../../.github/workflows/check.yml)는 GitHub Actions의 소스 점검·백엔드 계약·프런트 타입/빌드·브라우저 모형 시험을 구성한다. Actions는 확인한 commit SHA, uv와 Node는 버전, 앱 의존성은 lockfile로 고정했다. 저장소 읽기 권한만 사용하며 checkout 인증을 보존하지 않는다. 외부 계정 자격증명은 필요 없다.

구성 추가와 로컬 명령 검증은 GitHub 호스팅 실행 성공과 다르다. 원격 커밋별 결과는 위 Actions 링크에서 확인한다. 공식 동작 기준: [checkout](https://github.com/actions/checkout), [setup-node](https://github.com/actions/setup-node), [setup-uv](https://github.com/astral-sh/setup-uv). 이 CI는 네이티브 Windows/macOS·실계정 재로그인·Codex 사용자 확인·실제 KURE 검색을 대체하지 않는다.

## 의존성·라이선스·공개 범위

`npm audit`와 Python `pip-audit` 결과는 조회 시점의 알려진 취약점만 확인한다. 자체 코드·모델 공급망·원격 계정 계약의 전체 안전성을 인증하지 않는다. 최종 점검에 조회 날짜, 제외된 패키지와 처리 방법을 남긴다.

프로젝트 코드의 배포 라이선스는 아직 선택되지 않았다. 저작권자의 선택이 필요한 항목이므로 임의로 MIT 등의 라이선스를 추가하지 않았다. 원격 저장소의 공개/비공개와 프로젝트 라이선스를 결정하고, 재배포할 번들·글꼴·모델의 고지 범위를 확인한 뒤 공개 배포 여부를 정한다. 기존 글꼴과 프로토타입 vendor 라이선스 고지는 보존한다. 모델 가중치는 저장소에 포함하지 않는다.

원격 등록 준비와 제품 출시 준비는 다르다. 원격 저장소에 코드를 보관할 수 있어도 [플랫폼 관문](../architecture/platform-support.md), 사용자 보류 재로그인, 실제 한국어 사용 품질과 대규모 성능은 계속 추적한다.
