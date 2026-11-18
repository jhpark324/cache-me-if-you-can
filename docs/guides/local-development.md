# 로컬 설치·실행

**Cache Me If You Can**은 로컬 기록 저장소와 웹 화면을 제공한다. 기록 관리 스킬과 실행 명령은 **cache-me**, Python 패키지와 MCP 등록 키는 `cache_me`, 서버 표시 이름은 **Cache Me If You Can**이다. 현재 개발 버전은 `0.7.0`이며 [버전 정책](versioning.md)을 따른다.

실행을 확인한 환경은 WSL Linux x64, Python 3.12, CPU다. Windows·macOS·Linux 네이티브 지원의 상태와 패키지 제약은 [지원 환경](../architecture/platform-support.md)을 따른다.

## 처음 실행

Python 실행기, [uv](https://docs.astral.sh/uv/), Node.js 22와 npm을 준비한 뒤 프로젝트 루트에서 실행한다. Windows에서는 `python` 대신 `py -3`을 사용할 수 있다. uv가 제품용 Python 3.12와 가상환경을 관리한다.

```sh
python scripts/manage.py setup
python scripts/manage.py run
```

`setup`은 잠금 파일에 따라 의존성을 설치하고 웹을 빌드한다. `run`은 터미널에서 서버를 실행하며 `Ctrl+C`로 종료한다. 서버는 loopback 주소에만 바인딩하며, 기본 웹 주소는 [http://127.0.0.1:52761/](http://127.0.0.1:52761/)이다.

준비된 서버를 터미널과 분리해 실행하려면 다음 명령을 사용한다. `start`는 준비 완료를 확인한 뒤 반환하고, 같은 데이터 경로·포트의 정상 서버가 이미 있으면 재사용한다. `doctor`는 서버를 시작하거나 설정을 고치지 않고 상태를 진단한다.

```sh
python scripts/manage.py start
python scripts/manage.py doctor
```

1. **새 기록**에서 Markdown 본문을 저장한다. 저장·조회·정정·확인 후 삭제에는 AI 로그인이 필요하지 않다.
2. 설정에서 **검색 모델 준비**를 실행한다. 최초에는 KURE-v2 고정 revision을 내려받고 CPU에서 로드한다.
3. **Continue with ChatGPT**로 로그인한 뒤 계정에서 제공하는 답변 모델을 선택한다. API key 입력은 필요 없다.
4. 색인이 준비되면 질문을 입력하고 답변의 출처를 확인한다. 질문과 답변은 자동으로 영구 저장되지 않는다.

검색 모델은 서버를 시작할 때마다 준비하며, 내려받은 파일은 캐시를 재사용한다. 기록 저장 직후에는 색인 작업이 진행 중일 수 있다. 자동 주제 연결은 로그인·모델 선택이 필요하고, 본문 저장·검색 색인과 별개로 처리된다. 분류가 실패한 기록은 **다시 분류**로 재시도할 수 있다.

## 실행 설정

| 환경 변수 | 의미 |
| --- | --- |
| `CACHE_ME_DATA_DIR` | SQLite·검색 색인·로컬 인증 파일 디렉터리. 기본값은 platformdirs의 `CacheMe` 사용자 데이터 경로 |
| `CACHE_ME_PORT` | 기본 52761. 웹·MCP·OAuth callback·Vite 개발 프록시에 사용 |
| `CACHE_ME_MODEL_PATH` | 선택 사항. 고정 KURE-v2 snapshot 또는 이를 포함한 Hugging Face 캐시 경로 |
| `CACHE_ME_DEV_ORIGIN` | Vite 개발 화면을 사용할 때 허용할 정확한 origin |

모델 revision은 `3431f86d399d666083890dbb882aced6708873bc`이다. 모델 파일을 직접 지정할 때도 같은 revision을 사용한다. 데이터 디렉터리에는 개인 기록과 인증 파일이 있으므로 버전 관리나 공개 공유 대상에 넣지 않는다.

`52761`은 이 앱의 설정 가능한 기본 포트이며 시스템에 예약된 포트는 아니다. 웹과 MCP는 같은 loopback 서버를 사용하고 MCP 주소는 `http://127.0.0.1:52761/mcp/`다. 다른 프로그램이 점유하면 시작을 거부한다. 해당 프로그램을 임의로 종료하거나 빈 포트로 자동 이동하지 않으며, 필요하면 `CACHE_ME_PORT`를 명시해 변경한다.

기본값은 Dynamic/Private 범위 `49152–65535`에 속한다. [RFC 6335 §8.1.2](https://www.rfc-editor.org/rfc/rfc6335.html#section-8.1.2)는 이 범위의 로컬 사용을 허용하며 특정 번호의 영구 가용성을 가정하지 않도록 한다. [RFC 7605 §7.1](https://www.rfc-editor.org/rfc/rfc7605.html#section-7.1)의 동일 호스트 통신에서 설정 파일·URI로 포트를 전달하는 방식이 이 앱의 설치 구조와 맞으므로 `52761`을 유지한다. 이 숫자가 다른 모든 번호보다 충돌이 적다는 실측 근거는 없다.

운영체제의 임시 클라이언트 포트와도 겹친다. 기본 범위는 [Linux](https://docs.kernel.org/networking/ip-sysctl.html#ip-variables)에서 `32768–60999`, [Windows](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/default-dynamic-port-range-tcpip-chang)에서 `49152–65535`이며 실제 설정은 달라질 수 있다. 이 때문에 시작 시 점유·서버 식별 검사를 유지한다. 임시 범위를 피하려고 현재 미등록인 User Port를 택해도 향후 할당이나 다른 앱의 사용을 막을 수 없다. [RFC 7605 §7.8](https://www.rfc-editor.org/rfc/rfc7605.html#section-7.8)

## 웹 개발

제품 서버는 `frontend/dist`를 제공한다. 프런트엔드 소스를 바꾼 뒤 제품 서버에서 확인하려면 다시 빌드한다.

```sh
npm --prefix frontend run build
```

Vite의 개발 서버를 사용할 때는 백엔드를 `CACHE_ME_DEV_ORIGIN=http://127.0.0.1:5173`으로 실행한 뒤 별도 터미널에서 다음 명령을 실행한다. 셸에 맞는 환경 변수 설정 문법을 사용한다.

```sh
npm --prefix frontend run dev
```

백엔드 포트를 바꿨다면 Vite를 실행하는 터미널에도 같은 `CACHE_ME_PORT`를 설정한다. 지정하지 않으면 프록시는 기본 포트 `52761`을 사용한다.

## Codex MCP

다음 명령으로 준비된 서버를 시작하고 스킬과 MCP 연결을 현재 Codex 사용자 설정에 설치한다.

```sh
python scripts/manage.py start
python scripts/manage.py install-codex
python scripts/manage.py doctor
```

설치기는 사용자 Codex 홈의 `config.toml`에 MCP 연결 하나를 등록한다. 기록 관리용 [cache-me](../skills/cache-me/SKILL.md)는 `skills/cache-me/`에, 학습 아티클 작성용 [cache-me-article](../skills/cache-me-article/SKILL.md)은 `skills/cache-me-article/`에 설치한다. 두 스킬에는 각자의 UI metadata와 같은 웹 주소를 담은 `runtime.json`이 있다. `CODEX_HOME`이 없거나 비어 있으면 `~/.codex`를 사용한다. 이 사용자 설정은 같은 Codex 홈을 사용하는 프로젝트 없는 대화에서도 적용된다. 실행 중인 Codex가 연결을 다시 읽도록 하거나 새 대화에서 사용한다.

`runtime.json`에는 `schema_version: 1`, MCP 등록 이름 `mcp_server: "cache_me"`, 설치한 Python·데이터 경로·포트·웹/MCP 주소와 진단·시작 명령이 들어가며 토큰은 포함하지 않는다. 이 파일은 설치 시 생성되므로 저장소의 스킬 원본에는 없다.

```text
$cache-me 오늘 배운 트랜잭션 격리 수준을 정리해서 저장해줘.
$cache-me 지난번 복습 계획을 찾아줘.
$cache-me-article 트랜잭션 격리 수준에 대해 공부한 기록을 찾아 예시와 함께 아티클로 작성해줘.
```

스킬 목록에서 **cache-me**를 선택하거나 자연어로 `cache-me, …`라고 요청할 수도 있다. 자연어 선택은 스킬 설명과 요청 의도에 따라 이뤄진다. [스킬의 동작 범위](../specs/cache-me.md)를 참고한다.

기존 설치에 아티클 스킬을 추가할 때도 `python scripts/manage.py install-codex`를 실행한다. 설치기는 쓰기 전에 두 스킬과 MCP 설정의 충돌을 검사한다. 관리 파일이 달라 갱신이 필요한 경우 차이를 확인한 후 `python scripts/manage.py install-codex --replace`를 사용한다. 다른 스킬과 외부에서 작성한 MCP 설정은 보존한다. 설치는 실행 호스트의 Python 경로를 등록하므로 다른 OS나 가상환경으로 옮겼다면 해당 환경에서 다시 설치한다.

연결 설정을 영구 설치하지 않고 Codex CLI를 실행하려면 다음 명령을 사용한다. 자식 Codex는 `cache_me`로 연결하며 로컬 MCP 인증은 자식 프로세스에 전달된다. 이 명령은 기존 설정 파일을 자동으로 수정하지 않는다.

```sh
python scripts/manage.py codex
```

MCP endpoint는 `/mcp/`이다. 설치된 연결은 `http_headers_helper`로 보호된 앱 토큰을 읽고 설정 파일에는 토큰 자체를 복사하지 않는다. 헤더 helper는 인증 정보를 제공하며 서버를 시작하지 않는다. 서버 시작은 `start`의 명시적인 실행으로 처리한다. 삭제는 클라이언트의 사용자 재확인을 거치며, 거부·취소 또는 확인 미지원 시 실행되지 않는다. [연결 검사](testing.md#codex-mcp와-스킬)를 참고한다.

### 포트 변경

사용할 포트를 바꾸려면 같은 데이터 디렉터리를 유지하고, 직접 실행한 현재 서버를 먼저 종료한 뒤 새 포트로 시작한다. 포트 변경은 기록 이동이나 데이터 초기화가 아니다.

다음은 POSIX 셸에서 기본 포트로 이전하는 예시다. 사용자 지정 데이터 경로를 사용했다면 모든 명령에 기존 `CACHE_ME_DATA_DIR`를 유지한다.

```sh
CACHE_ME_PORT=52761 python scripts/manage.py start
CACHE_ME_PORT=52761 python scripts/manage.py install-codex --replace
CACHE_ME_PORT=52761 python scripts/manage.py doctor
```

PowerShell에서는 먼저 `$env:CACHE_ME_PORT = "52761"`을 설정하고 같은 명령을 실행한다. 기존 포트를 유지하거나 다른 포트를 선택하려면 위 값만 원하는 포트로 바꾼다. `--replace`는 관리 연결·스킬의 갱신을 명시하며 다른 설정과 사용자 기록을 보존한다. 기존 서버를 자동 종료하지 않으므로 같은 저장소가 이전 포트에서 실행 중이면 먼저 해당 프로세스를 확인한다. 이후 Codex의 연결을 다시 읽거나 새 세션을 연다.

## 백업과 새 환경의 데이터 배치

설정의 **내 데이터 → 백업 다운로드**는 일관된 SQLite snapshot `cache-me.sqlite3`와 `manifest.json`을 `cache-me-YYYY-MM-DD.zip`으로 내려받는다. 내부 삭제 이력도 포함되며 로그인 비밀·모델 가중치·검색 색인은 제외한다. 현재 가져오기·복원 화면과 휴지통은 제공하지 않는다. [백업 계약](../specs/runtime.md)을 참고한다.

다른 PC에서는 같은 버전의 소스를 준비하고 `setup`을 실행한다. 서버를 처음 시작하기 전에 백업의 SQLite snapshot을 새 빈 데이터 디렉터리에 `cache-me.sqlite3`로 배치한다. 이전 개발본에서 내보낸 snapshot도 기록 스키마가 같다면 이 파일명으로 명시적으로 복사할 수 있다. 기존 데이터가 있는 디렉터리에는 덮어쓰거나 병합하지 않는다. 실행 중인 DB 파일을 직접 복사하는 대신 앱의 일관된 백업을 사용한다.

`CACHE_ME_DATA_DIR`를 지정하지 않았을 때 기본 경로는 Linux의 `~/.local/share/CacheMe/`, macOS의 `~/Library/Application Support/CacheMe/`이다. OS별 데이터 경로 환경 변수나 직접 지정한 `CACHE_ME_DATA_DIR`가 있으면 해당 경로를 사용한다. 실행기는 이전 이름의 경로를 자동 탐색하지 않는다.

이후 `start`, `install-codex`, `doctor`를 실행하고 Codex 연결을 다시 읽는다. 웹에서 **검색 기능 준비**를 실행하면 누락된 검색 색인을 다시 만든다. AI 답변·자동 주제 연결을 사용하려면 ChatGPT에 다시 로그인하고 모델을 선택한다. 기록 조회와 실제 검색을 확인할 때까지 원본과 백업을 보관한다.

## 문제 해결

- **검색 모델 준비 실패:** 저장은 계속 사용할 수 있다. 모델 파일 경로·고정 revision·네트워크와 [플랫폼 제약](../architecture/platform-support.md)을 확인한다.
- **새 기록이 검색되지 않음:** 색인 상태를 확인한다. 준비 중이거나 실패한 색인을 기록 없음으로 해석하지 않는다.
- **자동 주제 연결 실패:** 로그인·선택 모델을 확인한 뒤 해당 기록의 다시 분류를 실행한다.
- **MCP 연결 실패:** `python scripts/manage.py doctor`로 런타임·설치 설정·인증 준비 상태를 먼저 확인한다. 설치된 스킬에서 진단한다면 옆의 `runtime.json`에 있는 `commands.doctor`를 사용해 설치 당시의 Python·데이터 경로·포트를 검사한다. 토큰이나 인증 파일 내용을 오류 보고에 첨부하지 않는다.
- **MCP 설정이 없거나 불일치함:** `doctor`는 현재 `cache_me` 연결을 검사한다. 미설치이면 `install-codex`, 현재 이름의 관리 설정 갱신이면 `install-codex --replace`를 실행한다. 외부 작성 설정이나 손상된 관리 구간은 자동으로 덮어쓰지 않는다. 다른 이름의 연결은 진단·이전 대상이 아니다.
- **서버 미실행:** 설치와 의존성이 준비되어 있다면 `start`로 시작한다. 다른 앱의 포트 점유, 다른 데이터 경로의 서버 또는 같은 저장소의 다른 포트 실행은 별도로 해결한다. `start`를 반복해도 이러한 충돌을 덮어쓰지 않는다.
- **서버는 정상인데 MCP 도구가 없음:** 건강 응답은 현재 Codex 대화의 도구 목록 갱신을 보장하지 않는다. 설정 불일치가 없다면 연결을 다시 읽거나 새 세션을 연다. 작성한 본문을 보존하고 실제 MCP 저장 결과를 확인하기 전에는 등록 완료로 처리하지 않는다.
- **설치된 스킬에 `runtime.json`이 없음:** 위 설치 절차로 관리 스킬을 갱신한다. 에이전트가 의존성 설치나 사용자 설정 덮어쓰기를 자동 복구처럼 실행하지 않도록 한다.

재사용할 [합성 예제](../examples/conversations/index.md)와 [검사 실행 방법](testing.md)을 별도로 제공한다.
