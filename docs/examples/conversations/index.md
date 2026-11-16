# 합성 대화와 기록 예제

[dataset.json](dataset.json)은 가상 대화에서 사용자가 저장을 요청한 내용을 정리본으로 남기는 40개 사례다. 실제 사용자 대화나 실제 모델 실행 결과가 아니다. 제품에는 정리한 기록만 저장하며 대화 전체를 자동 수집하지 않는다.

각 사례는 가상 대화, 명시적인 저장 요청, 기대 저장 내용, 검색 질문과 기대 근거를 포함한다. 지식·경험·맥락·아이디어·결정·자료의 여섯 유형과 미분류·복수 유형, 긴 본문 후반 검색, 미채택 제안, 완료 상태, 원문 출처를 다룬다. 모든 제목은 `[테스트]`로 표시된다.

## 자료 검증

프로젝트 루트에서 실행한다. 기본 명령과 `validate`는 자료만 검사하며 서버에 연결하거나 기록을 추가하지 않는다.

```sh
python3 scripts/seed_conversations.py validate
```

유형, 합성 자료 표시, 제목·본문, 명시적인 저장 요청, 실제 본문에 포함된 근거, 선행 기록의 출처, Node의 정확한 문자 구간을 검사한다. 사용자 정의 자료는 `--dataset`으로 지정할 수 있지만 현재 배치·사례 계약을 충족해야 한다.

## 별도 데모 저장소에서 실행

설치가 완료된 환경에서 데모 전용 서버를 실행한다. 아래 경로는 Git에서 제외되는 `.local/` 아래의 별도 저장소이며, 사용 중인 개인 기록의 경로를 지정하지 않는다.

```sh
CACHE_ME_DATA_DIR="$PWD/.local/example-data" CACHE_ME_PORT=8010 \
  backend/.venv/bin/python -m cache_me.main
```

데모 서버의 설정 화면에서 검색 모델을 준비한다. 자동 주제 연결이 필요하면 이 서버에서 모델에 로그인하고 답변 모델을 선택한다. 원문 저장은 로그인 없이 가능하며, 주제 연결·검색 준비의 성공은 별도로 확인한다.

다른 터미널에서 프로젝트 루트로 이동한 후 실행한다. **`import`는 지정한 저장소에 테스트 기록 40개를 추가한다.**

```sh
backend/.venv/bin/python scripts/seed_conversations.py import \
  --data-dir "$PWD/.local/example-data" --url http://127.0.0.1:8010/mcp/
```

같은 저장소에서 같은 배치를 다시 실행하면 기존 manifest와 요청 ID로 커밋 결과를 확인하여 중복을 막는다. 이미 저장한 배치의 저장 payload를 변경해 재사용하지 않는다. 다른 저장소의 manifest를 복사하지 않는다.

색인과 주제 연결 작업이 종료된 뒤 검색·원문을 확인한다. 색인이 준비 중이면 `verify`는 성공으로 처리하지 않는다.

```sh
backend/.venv/bin/python scripts/seed_conversations.py verify \
  --data-dir "$PWD/.local/example-data" --url http://127.0.0.1:8010/mcp/
```

기본 실행 manifest와 보고서는 지정한 데이터 디렉터리의 `conversation-imports/`에 저장된다. 공개 문서나 데이터셋에 실행별 ID와 응답을 누적하지 않는다. 위 명령은 POSIX 셸 문법이다. Windows에서는 사용하는 셸의 환경 변수 설정 문법과 `backend\.venv\Scripts\python.exe` 실행기 경로를 사용한다. 설치와 지원 환경은 [로컬 실행 가이드](../../guides/local-development.md)를 따른다.

## 평가 범위

`verify`는 기대 기록의 검색 결과, 근거 구간·원문 버전, Node 위치, 색인 상태, 기존 기록의 보존을 확인한다. 합성 자료의 검색 성공을 일반적인 답변 품질로 확대하지 않는다. `avoid_claims`는 의미 검토를 위한 기대 조건이며 문자열 검사만으로 사실성을 보증하지 않는다.

[예제 목록](../index.md) · [기록 명세](../../specs/records.md) · [검사 방법](../../guides/testing.md)
