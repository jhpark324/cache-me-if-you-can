# 로컬 설치·실행

**Cache Me If You Can**은 로컬 기록 저장소와 웹 화면을 제공한다. 기록 관리 스킬은 **cache-me**, Python 모듈과 MCP 서버 키는 `second_brain`이다.

실행을 확인한 환경은 WSL Linux x64, Python 3.12, CPU다. Windows·macOS·Linux 네이티브 지원의 상태와 패키지 제약은 [지원 환경](../architecture/platform-support.md)을 따른다.

## 처음 실행

Python 실행기, [uv](https://docs.astral.sh/uv/), Node.js 22와 npm을 준비한 뒤 프로젝트 루트에서 실행한다. Windows에서는 `python` 대신 `py -3`을 사용할 수 있다. uv가 제품용 Python 3.12와 가상환경을 관리한다.

```sh
python scripts/manage.py setup
python scripts/manage.py run
```

`setup`은 잠금 파일에 따라 의존성을 설치하고 웹을 빌드한다. 서버는 loopback 주소에만 바인딩하며, 기본 웹 주소는 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)이다.

1. **새 기록**에서 Markdown 본문을 저장한다. 저장·조회·정정·확인 후 삭제에는 AI 로그인이 필요하지 않다.
2. 설정에서 **검색 모델 준비**를 실행한다. 최초에는 KURE-v2 고정 revision을 내려받고 CPU에서 로드한다.
3. **Continue with ChatGPT**로 로그인한 뒤 계정에서 제공하는 답변 모델을 선택한다. API key 입력은 필요 없다.
4. 색인이 준비되면 질문을 입력하고 답변의 출처를 확인한다. 질문과 답변은 자동으로 영구 저장되지 않는다.

검색 모델은 서버를 시작할 때마다 준비하며, 내려받은 파일은 캐시를 재사용한다. 기록 저장 직후에는 색인 작업이 진행 중일 수 있다. 자동 주제 연결은 로그인·모델 선택이 필요하고, 본문 저장·검색 색인과 별개로 처리된다. 분류가 실패한 기록은 **다시 분류**로 재시도할 수 있다.

## 실행 설정

| 환경 변수 | 의미 |
| --- | --- |
| `SECOND_BRAIN_DATA_DIR` | SQLite·검색 색인·로컬 인증 파일 디렉터리. 기본값은 platformdirs의 `SecondBrain` 사용자 데이터 경로 |
| `SECOND_BRAIN_PORT` | 기본 8000. 웹 주소와 OAuth callback에 사용 |
| `SECOND_BRAIN_MODEL_PATH` | 선택 사항. 고정 KURE-v2 snapshot 또는 이를 포함한 Hugging Face 캐시 경로 |
| `SECOND_BRAIN_DEV_ORIGIN` | Vite 개발 화면을 사용할 때 허용할 정확한 origin |

모델 revision은 `3431f86d399d666083890dbb882aced6708873bc`이다. 모델 파일을 직접 지정할 때도 같은 revision을 사용한다. 데이터 디렉터리에는 개인 기록과 인증 파일이 있으므로 버전 관리나 공개 공유 대상에 넣지 않는다.

## 웹 개발

제품 서버는 `frontend/dist`를 제공한다. 프런트엔드 소스를 바꾼 뒤 제품 서버에서 확인하려면 다시 빌드한다.

```sh
npm --prefix frontend run build
```

Vite의 개발 서버를 사용할 때는 백엔드를 `SECOND_BRAIN_DEV_ORIGIN=http://127.0.0.1:5173`으로 실행한 뒤 별도 터미널에서 다음 명령을 실행한다. 셸에 맞는 환경 변수 설정 문법을 사용한다.

```sh
npm --prefix frontend run dev
```

## Codex MCP

제품 서버를 실행한 상태에서 다음 명령으로 스킬과 MCP 연결을 현재 Codex 사용자 설정에 설치한다.

```sh
python scripts/manage.py install-codex
```

[cache-me 스킬](../skills/cache-me/SKILL.md)과 UI metadata는 `$CODEX_HOME/skills/cache-me/`에 설치된다. `CODEX_HOME`이 없으면 `~/.codex/skills/cache-me/`를 사용한다. 실행 중인 Codex가 연결을 다시 읽도록 하거나 새 세션에서 사용한다.

```text
$cache-me 오늘 배운 트랜잭션 격리 수준을 정리해서 저장해줘.
$cache-me 지난번 복습 계획을 찾아줘.
```

스킬 목록에서 **cache-me**를 선택하거나 자연어로 `cache-me, …`라고 요청할 수도 있다. 자연어 선택은 스킬 설명과 요청 의도에 따라 이뤄진다. [스킬의 동작 범위](../specs/cache-me.md)를 참고한다.

설치기는 다른 스킬·MCP 설정을 보존한다. 설치된 관리 파일을 갱신할 때는 `install-codex --replace`를 사용하며, 외부에서 작성한 같은 MCP 설정은 자동 교체하지 않는다. 설치는 실행 호스트의 Python 경로를 등록하므로 다른 OS나 가상환경으로 옮겼다면 해당 환경에서 다시 설치한다.

연결 설정을 영구 설치하지 않고 Codex CLI를 실행하려면 다음 명령을 사용한다. 로컬 MCP 인증은 자식 프로세스에 전달된다.

```sh
python scripts/manage.py codex
```

MCP endpoint는 `/mcp/`이다. 설치된 연결은 `http_headers_helper`로 보호된 앱 토큰을 읽고 설정 파일에는 토큰 자체를 복사하지 않는다. 삭제는 클라이언트의 사용자 재확인을 거치며, 거부·취소 또는 확인 미지원 시 실행되지 않는다. [연결 검사](testing.md#codex-mcp와-스킬)를 참고한다.

## 백업

설정의 수동 백업은 일관된 SQLite snapshot과 manifest를 ZIP으로 내려받는다. 내부 삭제 이력도 포함되며 로그인 비밀·모델 가중치·검색 색인은 제외한다. 현재 가져오기·복원 화면과 휴지통은 제공하지 않는다. [기록 수명과 백업 계약](../specs/records.md)을 참고한다.

## 문제 해결

- **검색 모델 준비 실패:** 저장은 계속 사용할 수 있다. 모델 파일 경로·고정 revision·네트워크와 [플랫폼 제약](../architecture/platform-support.md)을 확인한다.
- **새 기록이 검색되지 않음:** 색인 상태를 확인한다. 준비 중이거나 실패한 색인을 기록 없음으로 해석하지 않는다.
- **자동 주제 연결 실패:** 로그인·선택 모델을 확인한 뒤 해당 기록의 다시 분류를 실행한다.
- **MCP 연결 실패:** 제품 서버와 설치한 Python·데이터 경로가 같은 환경을 가리키는지 확인한다. 토큰이나 인증 파일 내용을 오류 보고에 첨부하지 않는다.

재사용할 [합성 예제](../examples/conversations/index.md)와 [검사 실행 방법](testing.md)을 별도로 제공한다.
