# 저장·검색·출처의 실행 흐름

2026-11-02 구현 기준이다. [현재 시스템](current-system.md)의 모듈과 [공통 계약](service-contracts.md)을 시간 순서로 설명한다. 다이어그램의 실패 경로는 데이터 폐기를 뜻하지 않는다.

## 저장과 비동기 처리

```mermaid
sequenceDiagram
    actor User as 사용자/명시적 요청
    participant API as 웹 API 또는 MCP
    participant Records as RecordService
    participant SQL as SQLite
    participant Jobs as worker
    participant Model as CPU 임베딩 / 외부 분류 모델
    participant Lance as LanceDB
    User->>API: 본문·선택 Node·힌트 + request_id
    API->>Records: 입력·출처·권한 검증
    Records->>SQL: 짧은 트랜잭션 시작
    Records->>SQL: Capture + Revision + receipt + jobs
    SQL-->>Records: commit
    Records-->>User: 실제 저장본·검색/분류 상태
    Jobs->>SQL: 현재 작업 claim / lease
    Jobs->>Model: 트랜잭션 밖에서 처리
    alt 색인 작업
      Model-->>Jobs: 청크별 다중 벡터
      Jobs->>Lance: 파생 문서 upsert
      Jobs->>SQL: 현재 세대/버전 확인 후 ready
    else 주제 분류
      Model-->>Jobs: 기존 주제 ID / 신규 주제 제안
      Jobs->>Records: lease·revision·주제 version 재확인
      Records->>SQL: 연결 변경 시 새 revision 생성
    end
    Note over SQL,Lance: 분류 실패·모델 준비 실패에도 본문 저장은 유지
```

사용자 수동 주제 정정은 진행 중인 자동 분류보다 우선한다. 분류 결과가 늦게 와도 이전 본문으로 새 revision을 덮지 않는다. 주제 정정으로 revision과 Node ID도 달라질 수 있으므로 다음 작업은 응답의 최신 참조를 사용한다.

## 단일 질문과 답변

```mermaid
flowchart TD
    Input[질문 + 서버 고정 유형/주제/날짜 조건] --> Prepare[원 질문 구간·요청 예산 구성]
    Prepare --> Agent[create_agent 모델 판단]
    Agent --> Guard{읽기 도구 예산이 남았는가}
    Guard -->|총 8회 미만| Tools[search_knowledge / read_evidence]
    Tools -->|검색| Vector[KURE 질의 임베딩 + 정확 벡터 검색]
    Tools -->|검색| FTS[BM25 키워드 검색]
    Vector --> RRF[RRF 순위 통합]
    FTS --> RRF
    RRF --> Validate[SQLite 현재 revision·세대·삭제·출처 확인]
    Tools -->|기존 근거 ID 재조회| Validate
    Validate --> Context[서버 근거 장부·범위·관계]
    Context --> PII[PII 정제 후 도구 결과 전달]
    PII --> Agent
    Guard -->|한도 도달| Answer[추가 도구 없이 최종 JSON]
    Agent -->|근거 충분 또는 한계 인식| Answer
    Answer --> Check[별도 모델 근거 검토 + 버전/관계 재검증]
    Check --> Valid{여전히 유효한가}
    Valid -->|예| Retrieval[읽은 근거 구간 재검증·PII 라벨·최종 인용 표시]
    Retrieval --> SSE[SSE answer_part / completed]
    Valid -->|아니오| Stop[실패·무효화 반환]
    SSE --> Prose[하나의 설명 + 작은 출처 번호]
    SSE --> Overlay[읽은 청크·부모 연결을 임시 그래프에 표시]
    Prose --> Panel[출처 선택 → 정확한 revision/구간]
    Overlay --> Panel
```

현재 질문 실행은 LangGraph 기반 `create_agent`의 모델→읽기 도구→모델 ReAct 루프다. 모델이 재검색 순서와 질의를 선택하며, `search_knowledge`와 이미 찾은 근거의 `read_evidence`만 호출한다. 같은 응답에서 여러 도구를 요청해도 각각 집계하여 요청 전체 총 8회만 실행한다. 잘못된 인수·실패한 도구도 예산을 소비한다. 에이전트 모델 호출 최대 9회와 별도 검토 1회, 전체 요청 90초를 적용한다. 도구 한도에 도달하면 도구를 제거하고 현재 근거로 최종 응답을 작성하게 한다. 읽기 도구의 본문·기록 수 및 모델 입력 예산도 별도로 검사한다.

원 질문의 정확한 정제 후 질의와 일치하는 검색만 해당 구간의 coverage를 완료로 표시한다. 모델이 전달한 구간 ID나 요약만으로 완료 처리하지 않으며, 검색하지 않은 구간은 limitations에 남긴다. 질문·답변은 자동 영구 저장하지 않고 수정·삭제 도구도 연결하지 않는다. 이후 별도 검토는 주장·주체·시점·범위의 근거를 검사하고, 전송 직전에는 결정적인 버전·관계 재검증을 수행한다. 두 검사는 모든 문장의 사실 정확도를 보증하지 않는다. [구체적인 후속 계약](../specs/004-local-runtime/react-agent.md)

이메일·신용카드·IP는 내장 `PIIMiddleware`로 모델 입력과 반환 응답을 정제한다. 웹으로 내보내는 답변은 공급자 스트림 완료와 PII 정제·근거 검토를 마친 결과다. 원본 도구 결과를 스트리밍으로 먼저 노출하지 않는다. 저장 정본과 출처 위치는 바꾸지 않으며 자동 분류는 기존 LangGraph 흐름에서 같은 모델 경계의 PII 정제를 사용한다.

웹은 질문마다 `/questions`만 호출하고 완료된 답변을 하나의 글로 보여준다. 관련 기록을 위한 별도 `/search` 요청은 보내지 않는다. 작은 출처 번호는 검증된 문단과 연결되며, 선택하면 기존 오른쪽 패널을 연다. [읽기 경험 수용 기준](../specs/004-local-runtime/answer-reading.md)

`completed`에는 요청의 서버 근거 장부에서 가져온 검색 구간도 포함한다. 그래프는 읽은 청크와 실제 인용된 청크를 구별하며, 출처 번호와 청크 노드는 같은 SourceRef 전체 좌표를 사용한다. 저장된 지식 그래프를 변경하지 않고 화면에서만 합성하며, 별도 검색 호출을 추가하지 않는다. [검색 근거 그래프](../specs/004-local-runtime/retrieval-graph.md)

## 수정과 출처 자격

```mermaid
stateDiagram-v2
    [*] --> valid: 현재 revision과 출처 유효
    valid --> valid: 엄격한 의미 동등 메타데이터 변경
    valid --> source_changed: 본문/의미/범위 변경
    valid --> source_deleted: 출처 soft delete
    source_changed --> valid: 명시적 출처 재검토 후 새 revision
    source_deleted --> valid: 독립된 새 근거로 본문 재작성 + 재검토
    valid --> unavailable: 부모 기록 soft delete
    source_changed --> unavailable: 부모 기록 soft delete
    source_deleted --> unavailable: 부모 기록 soft delete
```

이 도식은 출처 조회 자격의 개념 상태다. 별도 `lifecycle_state` 필드를 추가하지 않는다. 저장된 옛 revision은 불변이며, “재검토 후 valid”는 새 revision의 자격이다. 의존 출처를 제거할 때는 본문 재작성이 필수이며, 출처 버전을 갱신하는 모든 재검토에 본문 변경을 강제하지는 않는다. 삭제한 부모 기록에는 조회·복원·실행 취소 경로가 없다. 출처 삭제는 독립 기록을 연쇄 삭제하지 않으며 의존 기록을 답변 근거에서 제외한다.

## 삭제 확인과 동시성

```mermaid
sequenceDiagram
    actor Human as 사용자
    participant Client as 웹 / Codex
    participant Service as RecordService
    participant DB as SQLite
    Client->>Service: prepare_delete(기대 revision/state)
    Service-->>Client: 대상에 묶인 확인 토큰
    Client->>Human: 이 기록을 삭제할까요?
    alt 승인
      Human-->>Client: 직접 확인
      Client->>Service: 확인 증거 + request_id
      Service->>DB: 토큰·세션·기대 버전 확인
      alt 확인 후 기록 변경
        DB-->>Client: 충돌 / 다시 확인 필요
      else 여전히 동일
        Service->>DB: deleted_at + state/index 세대 + outbox
        DB-->>Client: 커밋된 삭제 결과
      end
    else 거부 또는 미지원
      Client-->>Human: 삭제하지 않음
    end
```

MCP 모델 입력의 `confirmed=true` 같은 값으로 사람의 확인을 대체하지 않는다. 웹은 CSRF로 보호된 session-bound 확인 경로, MCP는 SDK의 elicitation 경로를 사용한다. 같은 요청 재시도는 mutation receipt를 재사용하고 다른 내용으로 request ID를 재사용하면 충돌한다.

## 로그인과 요청 취소

```mermaid
sequenceDiagram
    actor User as 사용자
    participant Web as 웹
    participant Auth as 서버 ModelAuth
    participant Provider as ChatGPT OAuth/모델
    User->>Web: Continue with ChatGPT
    Web->>Auth: 로그인 시작 + 웹 세션
    Auth-->>Web: state/nonce/PKCE 인가 URL
    Web->>Provider: 사용자가 직접 인증
    Provider->>Auth: loopback callback
    Auth->>Provider: code 교환·공개키/계약 확인
    Auth->>Auth: 서명·issuer·audience·nonce·계정 확인
    Auth-->>Web: 상태·모델 목록 (토큰 제외)
    Web->>Auth: 단일 질문
    Auth->>Provider: 필요 시 refresh + store=false 호출
    alt 취소/모델 변경/로그아웃
      Web->>Auth: 취소 또는 상태 변경
      Auth->>Auth: 실행 task·세대 무효화
      Auth-->>Web: cancelled 또는 오류
    else 완료
      Provider-->>Web: 서버를 통한 검증된 응답
    end
```

브라우저에는 공급자 토큰을 전달하지 않는다. HTTP callback query·질문·본문을 접근 로그에 기록하지 않도록 한다. 취소 후 결과가 도착해도 새 요청을 덮지 않아야 하며, 공급자의 원격 연산이 즉시 중단됐다고 보증하지 않는다. 실계정 로그아웃→재로그인 검증은 사용자가 보류한 상태다.
