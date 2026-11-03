# Cache Me If You Can 로컬 설치·실행

제품 이름은 **Cache Me If You Can**이다. 기존 설치와의 호환을 위해 `second_brain` 모듈·MCP 키, `$second-brain` 스킬 호출명, `SECOND_BRAIN_*` 환경 변수와 `SecondBrain` 데이터 경로는 유지한다. 이름 변경으로 기존 데이터를 옮기거나 다시 로그인할 필요가 없다.

현재 실행 검증은 WSL Linux x64의 Python 3.12·CPU 환경이다. Windows·macOS·Linux 네이티브 지원은 목표이며 [플랫폼별 미검증 사항](../architecture/platform-support.md)을 유지한다. 특히 Intel Mac과 Windows ARM의 네이티브 패키지 설치는 해결 전이다.

## 처음 실행

Python 실행기, uv, Node.js 22와 npm을 준비한 뒤 프로젝트 루트에서 실행한다. Windows에서 `python` 대신 `py`를 사용할 수 있다. uv가 제품용 Python 3.12와 격리 환경을 관리한다.

```sh
python scripts/manage.py setup
python scripts/manage.py run
```

웹 주소는 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)이다. 기존 4381 목데이터 시안과 별도다. 서버는 loopback에만 바인딩한다.

1. 빈 저장소에서 본문만으로 기록을 추가할 수 있다. AI 로그인 없이 저장·조회·정정·삭제가 동작한다.
2. 설정의 검색 모델 준비를 실행한다. KURE-v2 고정 revision을 최초 다운로드하고 CPU에서 로드한다. 다운로드 전후에 원본 기록은 보존된다. 준비 중/실패 상태를 성공으로 표시하지 않는다.
3. 설정의 **Continue with ChatGPT**에서 자체 로그인하고 계정에서 제공하는 답변 모델을 선택한다. API key 입력은 필요 없다.
4. 색인 준비 후 한국어 검색을 이용한다. AI 답변은 로그인·모델 선택 이후 생성된다. 검색과 답변은 자동 기록으로 저장하지 않는다.

현재 모델 로딩은 매 서버 시작 후 준비 버튼으로 시작한다. 이미 다운로드한 모델은 캐시를 사용한다. 기록 저장 후 주제 연결은 로그인·모델 선택 시 별도 작업으로 진행한다. 저장 상한 100,000 code points까지 본문 전체를 분할 분류한 뒤 한 번에 주제를 반영한다. 한 구간이 실패하면 부분 결과를 반영하지 않으며 기록의 **다시 분류**에서 실패 작업을 재시도할 수 있다. 본문 저장·청크 검색은 분류 상태와 별개다.

## 실행 설정

| 환경 변수 | 의미 |
| --- | --- |
| `SECOND_BRAIN_DATA_DIR` | SQLite·색인·보호된 로컬 인증 파일 디렉터리. 기본값은 platformdirs의 사용자 데이터 경로 |
| `SECOND_BRAIN_PORT` | 기본 8000. OAuth callback도 동일 포트 사용 |
| `SECOND_BRAIN_MODEL_PATH` | 선택 사항. KURE-v2 고정 snapshot 경로 또는 이를 포함한 HF 캐시 경로 |
| `SECOND_BRAIN_DEV_ORIGIN` | Vite 개발 화면을 사용할 때만 `http://127.0.0.1:5173` 등 정확한 origin 지정 |

모델 revision은 `3431f86d399d666083890dbb882aced6708873bc`이며 다른 snapshot을 임의로 혼용하지 않는다. 기존 조사 캐시를 재사용할 때에도 이 revision을 가리켜야 한다.

인증 파일은 원자적으로 쓰고 Unix에서 소유자 전용 권한을 적용한다. Windows의 실제 ACL 동작은 별도 검증 대상이다. 토큰 파일을 저장소에 넣거나 공유하지 않는다. 서버 로그에 질문·답변·OAuth callback query를 남기지 않도록 접근 로그를 끈다.

## Codex MCP

SDK는 `mcp==2.3.0`, endpoint는 `/mcp/`이다. 서버를 먼저 실행한 뒤 다음 명령으로 Codex CLI를 열면 로컬 MCP 토큰을 해당 자식 프로세스의 환경에만 주입한다. 토큰은 명령 출력이나 저장소 설정 파일에 기록하지 않는다.

```sh
python scripts/manage.py codex
```

자주 사용할 때는 다음 명령으로 스킬과 MCP 연결을 현재 Codex 사용자 설정에 설치한다.

```sh
python scripts/manage.py install-codex
```

스킬 원본은 [Cache Me If You Can 스킬](../skills/second-brain/SKILL.md)이며 `$CODEX_HOME/skills/second-brain/`(미지정 시 `~/.codex/skills/second-brain/`)에 설치된다. 같은 사용자 설정을 사용하는 Codex 앱/CLI에서 다시 연결하면 `$second-brain`으로 호출할 수 있다. 예: “`$second-brain 오늘 배운 트랜잭션 격리 수준을 정리해서 저장해줘`”.

MCP 설정의 `http_headers_helper`가 보호된 앱 토큰을 연결 시 읽는다. 설정에는 실행 경로와 데이터 경로만 들어가며 토큰을 복사하지 않는다. 헤더 제공 명령은 Codex가 실행하는 프로토콜이므로 터미널에서 직접 실행하거나 그 출력을 공유하지 않는다. 다른 스킬과 MCP 설정은 보존한다. 기존 설치의 경로·스킬을 갱신할 때는 `install-codex --replace`를 사용한다. 외부에서 작성된 같은 이름의 MCP 설정은 자동 교체하지 않는다.

설치 명령은 실행 호스트의 Python 경로를 등록한다. WSL에서 설치한 연결은 같은 WSL 호스트에서 사용하며, 다른 OS로 옮기면 그 환경에서 설치한다. 실행 중인 Codex는 연결을 다시 읽거나 재시작해야 할 수 있다. 실제 네이티브 OS 검증과는 구분한다.

다른 MCP 클라이언트는 같은 URL과 로컬 토큰으로 연결한다. 삭제 확인은 Streamable HTTP의 SSE 응답으로 전달한다. 확인을 지원하지 않거나 거부하는 클라이언트는 삭제하지 않는다. 자동화 검증과 실제 사람이 확인한 결과는 [004 검증 기록](../specs/004-local-runtime/validation.md)에서 구분한다.

격리된 임시 저장소에서 실제 Codex 연결을 검사할 수 있다. 기본 검사는 모델 호출 없이 생성·정정·조회와 삭제 확인의 거부/승인을 확인한다. 실제 모델 turn의 확인 경로는 현재 Codex 로그인을 사용하며 임시 기록만 다룬다.

```sh
uv run --project backend --extra embedding python scripts/check_codex.py
uv run --project backend --extra embedding python scripts/check_codex.py --model-turn --human
```

두 번째 검사는 첫 확인을 자동 거부하고 두 번째 확인에서 사람이 터미널에 `accept`를 입력해야 승인한다. 미입력/거부는 삭제 성공으로 기록하지 않는다. 프로그램이 대신 승인하는 기본 시험을 사람의 UI 승인으로 간주하지 않는다.

## 검사와 백업

```sh
python scripts/manage.py check
```

실제 임베딩 테스트는 `KURE_TEST_MODEL_PATH`를 고정 snapshot으로 지정한 경우만 실행하며 기본 검사는 이를 skip한다. OAuth 자동 검사는 실제 계정 로그인을 대신하지 않는다.

설정의 수동 백업은 SQLite의 일관된 snapshot과 manifest를 ZIP으로 내려받는다. 내부 보존된 삭제 이력도 포함되며 로그인 비밀·모델 가중치·검색 색인은 제외된다. 전체 데이터 백업이므로 공개 공유 파일로 취급하지 않는다. 가져오기·복원 화면과 휴지통은 제공하지 않는다.

현재 스택과 제품 검증 결과는 [004 검증 기록](../specs/004-local-runtime/validation.md)에서 확인한다.
