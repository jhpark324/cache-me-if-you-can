# 로컬 설치·실행

**Cache Me If You Can**은 로컬 기록 저장소와 웹 화면을 제공한다. 기록 관리 스킬은 **cache-me**, MCP 등록 키는 `cache_me`, 서버 표시 이름은 **Cache Me If You Can**이다. Python 패키지는 `second_brain`을 유지한다.

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
| `SECOND_BRAIN_DATA_DIR` | SQLite·검색 색인·로컬 인증 파일 디렉터리. 기본값은 platformdirs의 `SecondBrain` 사용자 데이터 경로 |
| `SECOND_BRAIN_PORT` | 기본 52761. 웹·MCP·OAuth callback·Vite 개발 프록시에 사용 |
| `SECOND_BRAIN_MODEL_PATH` | 선택 사항. 고정 KURE-v2 snapshot 또는 이를 포함한 Hugging Face 캐시 경로 |
| `SECOND_BRAIN_DEV_ORIGIN` | Vite 개발 화면을 사용할 때 허용할 정확한 origin |

모델 revision은 `3431f86d399d666083890dbb882aced6708873bc`이다. 모델 파일을 직접 지정할 때도 같은 revision을 사용한다. 데이터 디렉터리에는 개인 기록과 인증 파일이 있으므로 버전 관리나 공개 공유 대상에 넣지 않는다.

`52761`은 이 앱의 설정 가능한 기본 포트이며 시스템에 예약된 포트는 아니다. 웹과 MCP는 같은 loopback 서버를 사용하고 MCP 주소는 `http://127.0.0.1:52761/mcp/`다. 다른 프로그램이 점유하면 시작을 거부한다. 해당 프로그램을 임의로 종료하거나 빈 포트로 자동 이동하지 않으며, 필요하면 `SECOND_BRAIN_PORT`를 명시해 변경한다.

기본값은 Dynamic/Private 범위 `49152–65535`에 속한다. [RFC 6335 §8.1.2](https://www.rfc-editor.org/rfc/rfc6335.html#section-8.1.2)는 이 범위의 로컬 사용을 허용하며 특정 번호의 영구 가용성을 가정하지 않도록 한다. [RFC 7605 §7.1](https://www.rfc-editor.org/rfc/rfc7605.html#section-7.1)의 동일 호스트 통신에서 설정 파일·URI로 포트를 전달하는 방식이 이 앱의 설치 구조와 맞으므로 `52761`을 유지한다. 이 숫자가 다른 모든 번호보다 충돌이 적다는 실측 근거는 없다.

운영체제의 임시 클라이언트 포트와도 겹친다. 기본 범위는 [Linux](https://docs.kernel.org/networking/ip-sysctl.html#ip-variables)에서 `32768–60999`, [Windows](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/default-dynamic-port-range-tcpip-chang)에서 `49152–65535`이며 실제 설정은 달라질 수 있다. 이 때문에 시작 시 점유·서버 식별 검사를 유지한다. 임시 범위를 피하려고 현재 미등록인 User Port를 택해도 향후 할당이나 다른 앱의 사용을 막을 수 없다. [RFC 7605 §7.8](https://www.rfc-editor.org/rfc/rfc7605.html#section-7.8)

## 웹 개발

제품 서버는 `frontend/dist`를 제공한다. 프런트엔드 소스를 바꾼 뒤 제품 서버에서 확인하려면 다시 빌드한다.

```sh
npm --prefix frontend run build
```

Vite의 개발 서버를 사용할 때는 백엔드를 `SECOND_BRAIN_DEV_ORIGIN=http://127.0.0.1:5173`으로 실행한 뒤 별도 터미널에서 다음 명령을 실행한다. 셸에 맞는 환경 변수 설정 문법을 사용한다.

```sh
npm --prefix frontend run dev
```

백엔드 포트를 바꿨다면 Vite를 실행하는 터미널에도 같은 `SECOND_BRAIN_PORT`를 설정한다. 지정하지 않으면 프록시는 기본 포트 `52761`을 사용한다.

## Codex MCP

다음 명령으로 준비된 서버를 시작하고 스킬과 MCP 연결을 현재 Codex 사용자 설정에 설치한다.

```sh
python scripts/manage.py start
python scripts/manage.py install-codex
python scripts/manage.py doctor
```

[cache-me 스킬](../skills/cache-me/SKILL.md), UI metadata와 `runtime.json`은 `$CODEX_HOME/skills/cache-me/`에 설치된다. `CODEX_HOME`이 없으면 `~/.codex/skills/cache-me/`를 사용한다. `runtime.json`에는 `schema_version: 1`, MCP 등록 이름 `mcp_server: "cache_me"`, 설치한 Python·데이터 경로·포트·웹/MCP 주소와 진단·시작 명령이 들어가며 토큰은 포함하지 않는다. 이 파일은 설치 시 생성되므로 저장소의 스킬 원본에는 없다. 실행 중인 Codex가 연결을 다시 읽도록 하거나 새 대화에서 사용한다.

```text
$cache-me 오늘 배운 트랜잭션 격리 수준을 정리해서 저장해줘.
$cache-me 지난번 복습 계획을 찾아줘.
```

스킬 목록에서 **cache-me**를 선택하거나 자연어로 `cache-me, …`라고 요청할 수도 있다. 자연어 선택은 스킬 설명과 요청 의도에 따라 이뤄진다. [스킬의 동작 범위](../specs/cache-me.md)를 참고한다.

설치기는 `[mcp_servers.cache_me]`를 등록하고 다른 스킬·MCP 설정을 보존한다. 설치된 관리 파일을 갱신할 때는 `install-codex --replace`를 사용하며, 외부에서 작성한 같은 MCP 설정은 자동 교체하지 않는다. 이전 `second_brain` 연결이 있으면 아래 이름 이전 절차를 따른다. 설치는 실행 호스트의 Python 경로를 등록하므로 다른 OS나 가상환경으로 옮겼다면 해당 환경에서 다시 설치한다.

연결 설정을 영구 설치하지 않고 Codex CLI를 실행하려면 다음 명령을 사용한다. 자식 Codex는 `cache_me`로 연결하며 로컬 MCP 인증은 자식 프로세스에 전달된다. 기존 설정 파일에 `second_brain`이 있으면 실행 전에 이름 이전을 요구하고, 두 키가 모두 있으면 충돌로 거부한다. 이 명령은 기존 설정 파일을 자동으로 수정하지 않는다.

```sh
python scripts/manage.py codex
```

MCP endpoint는 `/mcp/`이다. 설치된 연결은 `http_headers_helper`로 보호된 앱 토큰을 읽고 설정 파일에는 토큰 자체를 복사하지 않는다. 헤더 helper는 인증 정보를 제공하며 서버를 시작하지 않는다. 서버 시작은 `start`의 명시적인 실행으로 처리한다. 삭제는 클라이언트의 사용자 재확인을 거치며, 거부·취소 또는 확인 미지원 시 실행되지 않는다. [연결 검사](testing.md#codex-mcp와-스킬)를 참고한다.

### 기존 MCP 이름에서 이전

이전 설치기의 관리 구간에 `[mcp_servers.second_brain]`이 있다면, 같은 Python 환경·데이터 경로·포트를 사용해 다음 명령으로 `cache_me`로 이전한다. 사용자 지정 `SECOND_BRAIN_DATA_DIR`와 `SECOND_BRAIN_PORT`가 있다면 기존 값을 유지한다.

```sh
python scripts/manage.py install-codex --replace
python scripts/manage.py doctor
```

`--replace`는 관리 구간의 등록 키와 설치된 스킬·의존성 정보를 함께 갱신한다. 기록·인증 파일·환경 변수·데이터 디렉터리와 `capture_create` 같은 개별 도구 이름은 바꾸지 않는다. 같은 상태에서 다시 설치해도 두 등록 키를 중복 생성하지 않는다. 이전 후에는 Codex 연결을 다시 읽거나 새 대화를 열어 `cache_me` 도구를 사용한다. 이미 열린 대화의 도구 이름은 서버 정상 응답만으로 갱신되지 않는다.

외부에서 직접 작성한 `second_brain` 연결, `second_brain`과 `cache_me`의 동시 존재, 불완전하거나 다른 설정을 포함한 관리 구간은 `--replace`로도 자동 교체하지 않는다. 설치기는 설정·스킬을 변경하기 전에 거부한다. `doctor` 결과와 해당 설정을 확인해 사용자가 충돌을 정리한 뒤 다시 설치한다. 포트도 바꾸려면 다음 절차를 함께 따른다.

### 기존 포트에서 이전

기존 `8000` 연결은 새 기본 포트로 자동 수정되지 않는다. 같은 데이터 디렉터리를 유지하고, 직접 실행한 이전 포트의 서버를 먼저 종료한 뒤 새 포트로 시작한다. 포트 변경은 기록 이동이나 데이터 초기화가 아니다.

다음은 POSIX 셸에서 기본 포트로 이전하는 예시다. 사용자 지정 데이터 경로를 사용했다면 모든 명령에 기존 `SECOND_BRAIN_DATA_DIR`를 유지한다.

```sh
SECOND_BRAIN_PORT=52761 python scripts/manage.py start
SECOND_BRAIN_PORT=52761 python scripts/manage.py install-codex --replace
SECOND_BRAIN_PORT=52761 python scripts/manage.py doctor
```

PowerShell에서는 먼저 `$env:SECOND_BRAIN_PORT = "52761"`을 설정하고 같은 명령을 실행한다. 기존 포트를 유지하거나 다른 포트를 선택하려면 위 값만 원하는 포트로 바꾼다. `--replace`는 관리 연결·스킬의 갱신을 명시하며 다른 설정과 사용자 기록을 보존한다. 기존 서버를 자동 종료하지 않으므로 같은 저장소가 이전 포트에서 실행 중이면 먼저 해당 프로세스를 확인한다. 이후 Codex의 연결을 다시 읽거나 새 세션을 연다.

## 백업

설정의 수동 백업은 일관된 SQLite snapshot과 manifest를 ZIP으로 내려받는다. 내부 삭제 이력도 포함되며 로그인 비밀·모델 가중치·검색 색인은 제외한다. 현재 가져오기·복원 화면과 휴지통은 제공하지 않는다. [기록 수명과 백업 계약](../specs/records.md)을 참고한다.

## 문제 해결

- **검색 모델 준비 실패:** 저장은 계속 사용할 수 있다. 모델 파일 경로·고정 revision·네트워크와 [플랫폼 제약](../architecture/platform-support.md)을 확인한다.
- **새 기록이 검색되지 않음:** 색인 상태를 확인한다. 준비 중이거나 실패한 색인을 기록 없음으로 해석하지 않는다.
- **자동 주제 연결 실패:** 로그인·선택 모델을 확인한 뒤 해당 기록의 다시 분류를 실행한다.
- **MCP 연결 실패:** `python scripts/manage.py doctor`로 런타임·설치 설정·인증 준비 상태를 먼저 확인한다. 설치된 스킬에서 진단한다면 옆의 `runtime.json`에 있는 `commands.doctor`를 사용해 설치 당시의 Python·데이터 경로·포트를 검사한다. 토큰이나 인증 파일 내용을 오류 보고에 첨부하지 않는다.
- **MCP 이름이 이전 값이거나 중복됨:** `doctor`로 미설치·이전 이름·두 이름의 동시 등록을 구분한다. 이전 관리 연결은 [MCP 이름 이전](#기존-mcp-이름에서-이전) 절차를 따르고, 외부 작성 설정이나 충돌은 확인 없이 덮어쓰지 않는다.
- **서버 미실행:** 설치와 의존성이 준비되어 있다면 `start`로 시작한다. 다른 앱의 포트 점유, 다른 데이터 경로의 서버 또는 같은 저장소의 다른 포트 실행은 별도로 해결한다. `start`를 반복해도 이러한 충돌을 덮어쓰지 않는다.
- **서버는 정상인데 MCP 도구가 없음:** 건강 응답은 현재 Codex 대화의 도구 목록 갱신을 보장하지 않는다. 설정 불일치가 없다면 연결을 다시 읽거나 새 세션을 연다. 작성한 본문을 보존하고 실제 MCP 저장 결과를 확인하기 전에는 등록 완료로 처리하지 않는다.
- **설치된 스킬에 `runtime.json`이 없음:** 위 설치 절차로 관리 스킬을 갱신한다. 에이전트가 의존성 설치나 사용자 설정 덮어쓰기를 자동 복구처럼 실행하지 않도록 한다.

재사용할 [합성 예제](../examples/conversations/index.md)와 [검사 실행 방법](testing.md)을 별도로 제공한다.
