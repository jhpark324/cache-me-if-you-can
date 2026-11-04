# 테스트

프로젝트 루트에서 명령을 실행한다. 의존성 설치는 [로컬 실행 가이드](local-development.md)를 따른다. 자동 계약 검사, 실제 외부 모델 검사, 운영체제 검증은 서로 다른 범위다.

## 기본 검사

```sh
python scripts/manage.py check
```

이 명령은 등록 후보·문서 링크, 스크립트 회귀, 백엔드 테스트, 웹 타입 검사와 빌드를 수행한다. 개별 범위만 확인할 때는 다음 명령을 사용한다.

```sh
python scripts/preflight.py
python -m unittest discover -s scripts/tests -v
uv run --locked --project backend --extra test pytest backend/tests -q
npm --prefix frontend run build
```

브라우저 검사는 별도로 실행한다. 기본 실행은 Vite 개발 서버와 모의 API를 사용한다.

```sh
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend test
```

Linux에서 브라우저 시스템 라이브러리가 없으면 `playwright install --with-deps chromium`을 사용한다. 테스트의 `skip`은 해당 조건을 실행하지 않았다는 뜻이며 통과로 세지 않는다. 변경 범위에 필요한 실제 API·모델 검사를 아래에서 선택한다.

## 로컬 시작과 연결 진단

포트·백그라운드 시작·진단·스킬 설치를 변경했다면 다음 검사를 실행한다. 자동 검사는 임시 경로와 합성 설정을 사용하며 사용자의 실제 기록과 Codex 설정을 수정하지 않는다.

```sh
uv run --locked --project backend --extra test pytest backend/tests/test_config.py backend/tests/test_local_runtime.py backend/tests/test_codex_integration.py -q
python -m unittest discover -s scripts/tests -p 'test_manage.py' -v
```

기본 포트 `52761`과 사용자 지정 포트의 일치, 잘못된 포트 거부, 같은 서버 재사용, 동시 시작, 다른 서비스·저장소 충돌, 시작 실패 정리, `doctor`의 읽기 전용 동작과 토큰 비노출을 확인한다. 설치 검사는 비밀 없는 `runtime.json`의 명령·주소, 반복 설치와 사용자 수정본 보호도 포함한다. 헤더 helper 호출만으로 서버가 시작되지 않아야 한다.

MCP 이름 검사는 새 `cache_me` 설치, 이전 `second_brain` 관리 연결의 명시적 이전, 반복 설치, 외부 설정·중복 키·손상된 관리 구간의 사전 거부를 확인한다. 거부 전후의 설정·스킬·데이터 파일을 비교하고, `doctor`가 이전 이름과 중복을 구분하는지 검사한다. 아래 실제 Codex 프로토콜 검사는 연결된 서버가 `cache_me` 하나이며 임시 저장소를 가리키는지 확인한다.

실제 Codex에서는 `doctor`가 정상이어도 현재 대화의 MCP 도구가 없을 수 있다. 연결 재로드 또는 새 세션에서 도구 목록을 확인하고, 격리 저장소에 대한 실제 도구 응답으로 저장 성공을 판단한다. 자동 테스트의 성공을 클라이언트 재연결이나 Windows·macOS 네이티브 실행을 확인한 것으로 기록하지 않는다. 실제 런타임을 수동 검사할 때도 아래 통합 검사처럼 새 빈 데이터 경로와 별도 포트를 사용한다.

## 실제 검색 모델

KURE-v2 고정 snapshot이 준비된 환경에서 `KURE_TEST_MODEL_PATH`를 지정한다. 미지정 시 실제 모델 테스트는 생략된다.

```sh
KURE_TEST_MODEL_PATH="/path/to/pinned-kure-v2-snapshot" \
uv run --locked --project backend --extra test --extra embedding \
pytest backend/tests/test_search_real_model.py -q
```

위 예시는 POSIX 셸 문법이다. PowerShell에서는 `$env:KURE_TEST_MODEL_PATH`를 설정하고 명령을 실행한다. 모델 revision과 입력 계약은 [검색·임베딩 구조](../architecture/search-and-embedding.md)를 따른다. 합성 자료에서 얻은 결과를 모든 사용자 기록의 정확도로 일반화하지 않는다.

## 실제 웹 API 통합

통합 검사는 기록을 생성·정정·삭제한다. 사용 중인 데이터 디렉터리와 다른 **새 빈 폴더** 및 사용하지 않는 포트에 서버를 띄운다. 아래는 POSIX 셸에서 프로젝트 루트의 `.local/integration-data`와 8016 포트를 사용하는 예시다. 이미 자료가 있다면 새 폴더 이름을 선택한다.

먼저 웹을 빌드하고, 첫 번째 터미널에서 격리 서버를 실행한다. 실패 작업 상태를 재현하는 검사와 경합하지 않도록 이 서버의 백그라운드 작업만 끈다.

```sh
npm --prefix frontend run build
SECOND_BRAIN_DATA_DIR="$PWD/.local/integration-data" SECOND_BRAIN_PORT=8016 \
uv run --locked --project backend --extra embedding python - <<'PY'
import uvicorn
from second_brain.config import Settings
from second_brain.main import create_app

settings = Settings.load()
settings.background_jobs = False
uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, access_log=False)
PY
```

두 번째 터미널에서도 프로젝트 루트에서 실행한다.

```sh
SECOND_BRAIN_TEST_URL=http://127.0.0.1:8016 \
SECOND_BRAIN_INTEGRATION=1 \
SECOND_BRAIN_QA_DATA_DIR="$PWD/.local/integration-data" \
npm --prefix frontend test -- tests/integration.spec.ts tests/management-integration.spec.ts
```

`SECOND_BRAIN_QA_DATA_DIR`는 위 서버의 데이터 경로와 같아야 한다. 이 경로의 SQLite에는 합성 자료만 있어야 한다. 이 검사는 실제 외부 AI 분류나 공급자 로그인 성공을 검증하지 않는다. 서버를 직접 지정하면 일부 Vite 전용 스트리밍 검사는 생략되므로 기본 브라우저 검사도 함께 실행한다.

## Codex MCP와 스킬

Codex CLI가 설치되어 있어야 한다. 프로토콜 검사는 자체 임시 저장소와 연결 설정을 사용한다.

```sh
uv run --locked --project backend --extra embedding python scripts/check_codex.py --decline-only
```

이 명령은 모델 호출 없이 생성·정정·조회와 삭제 거부 후 보존을 확인한다. 실제 모델이 삭제 요청을 수행하고 사람이 확인하는 경로를 검사하려면 다음 명령을 사용한다. 기존 Codex 로그인이 필요하고 모델 사용량이 발생한다.

```sh
uv run --locked --project backend --extra embedding python scripts/check_codex.py --model-turn --human
```

첫 삭제 확인은 자동 거부하고, 다음 확인에서 사람이 터미널에 `accept`를 입력한 경우만 승인한다. 프로그램의 응답을 사람의 UI 조작 검증으로 기록하지 않는다.

스킬의 저장·출처 조회·완료 변경·비트리거와 사용자 설치본 호출은 다음 명령으로 검사한다. 실행에는 기존 Codex 로그인이 필요하고 모델 사용량이 발생한다. 기록은 임시 저장소에만 쓰며, 결과는 버전 관리에서 제외된 로컬 폴더에 저장한다.

```sh
uv run --locked --project backend --extra embedding python scripts/check_cacheme_skill.py --output .local/checks/skill-behavior.json
uv run --locked --project backend --extra embedding python scripts/check_cacheme_skill.py --boundaries-only --output .local/checks/skill-boundaries.json
uv run --locked --project backend --extra embedding python scripts/check_cacheme_skill.py --global-only --output .local/checks/skill-installed.json
```

`--boundaries-only`는 저장 범위와 기록 단위에 대한 네 사례를 9턴으로 검사한다. 같은 대화에서 첫 주제를 저장한 뒤 다른 주제로 넘어가 최근 내용만 저장하는 경우, 전체 대화의 독립적인 내용을 각각 저장하는 경우, 하나의 결정과 이유를 함께 보존하는 경우, 여러 주제가 있는 한 문서의 원문을 보존하는 경우다. 기본 실행에도 이 사례들이 포함된다. 결과의 `thread_id`와 `turn_id`로 대화 재사용을 확인하고, 실제 저장된 기록의 개수·본문·공개 범위·서로 다른 요청 ID와 기존 기록 보존을 검사한다. 복수 저장의 부분 실패는 이 모델 검사에서 주입하지 않는다.

`--global-only` 실행 전에는 [cache-me 설치](local-development.md#codex-mcp)가 필요하다. 실제 모델의 선택은 요청과 모델에 따라 달라질 수 있으므로 한 실행의 성공을 모든 표현의 성공으로 해석하지 않는다. `scripts/tests/test_check_cacheme_skill.py`는 외부 의존성 없이 합성 app-server 스트림과 저장 결과로 검사 도구의 대화 재사용·알림 구분·실패 처리·판정 로직을 확인하며, 실제 모델의 행동을 검증한 결과는 아니다.

## CI와 수동 확인

[CI 구성](../../.github/workflows/check.yml)은 외부 계정 로그인 없이 소스 점검·계약 테스트·웹 빌드·모의 API 브라우저 검사를 실행한다. 실제 임베딩 모델, 외부 AI 품질, 사람의 확인창과 운영체제별 설치·권한 동작은 별도로 확인한다. 현재 확인한 환경과 남은 제약은 [플랫폼 지원](../architecture/platform-support.md)에 있다.

PR에는 실행한 명령과 결과, 생략한 범위를 적는다. 원문·인증 정보·개인 실행 로그를 공개 저장소에 추가하지 않는다. 보고서와 스크린샷은 민감한 내용을 제거한 CI 산출물 또는 로컬 작업 기록으로 보관한다.
