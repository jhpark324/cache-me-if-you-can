# ADR-003: 한국어 MVP에 KURE-v2 다중 벡터 임베딩 조건부 채택

- 상태: `accepted` — 개발 기준 채택, 전체 플랫폼 배포 승인은 별도
- 작성일: 2026-11-02
- 관련 기능·설계: [검색과 임베딩](../architecture/search-and-embedding.md), [기술 실험](../research/kure-v2-feasibility/report.md), [운영체제 지원](../architecture/platform-support.md)

## 배경

삭제 동작은 [ADR-006](ADR-006-soft-delete-without-trash.md)의 soft delete·조회 차단을 따른다. 연구의 상태 검증 모형은 제품의 휴지통·복원·영구 삭제 기능을 뜻하지 않는다.

CPU 기반 한국어 검색과 네이티브 실행 목표에 맞춰 KURE-v2 + MultiVectorEncoder + LanceDB를 평가했다. 고정 합성 자료와 사전 기준으로 수행한 WSL CPU 독립 실험을 선택 근거로 삼는다.

합성 기록 36개·질문 24개에서 MaxSim·하이브리드 모두 Hit@1과 Recall@5 1.000을 얻었다. 1,036개 짧은 합성 기록에서는 질문 인코딩부터 조정 후 ANN+RRF 검색까지 p95 약 0.252초, 본 실험 peak RSS 약 1.92GiB였다. PyLate 설치 없이 CPU 실행과 실제 ANN 계획을 확인했다. 자세한 범위·실패·원시 자료는 [보고서](../research/kure-v2-feasibility/report.md)에 둔다.

## 검토한 대안

| 대안 | 장점 | 단점 |
| --- | --- | --- |
| KURE-v2 + MultiVectorEncoder + LanceDB MaxSim | 한국어 중심 모델, 실제 CPU·다중 벡터·FTS 연결 확인, 작은 합성 평가에서 적절한 품질·자원 | 토큰별 벡터 저장 비용, ANN 후보 누락·입력 길이 계약, OS별 패키지 검증 필요 |
| KURE-v1 단일 벡터 | 단일 벡터 저장·검색 구조를 유지 | 더 큰 모델의 CPU 비용과 실제 품질은 비교하지 않음 |
| 기존 EmbeddingGemma 2 텍스트 전용 | 다국어 단일 벡터 접근 유지 | 한국어 중심 후속 요구에서 실제 검증한 모델을 우선할 근거가 생김 |
| PyLate + PLAID 추가 | 모델 제작자가 안내하는 검색 경로 | 이미 선택한 LanceDB 외의 색인·검색 수명 주기 추가; 현재 실험에 필수 아님 |

## 결정

한국어 중심 MVP의 기본 임베딩 개발 기준을 `nlpai-lab/KURE-v2`로 바꾼다. `MultiVectorEncoder` CPU float32, 토큰별 128차원, query expansion·문서 마스킹·정규화, LanceDB cosine MaxSim을 사용한다. 모델 revision과 입력 규칙을 프로필로 고정한다. 한 문서의 토큰 벡터를 평균 내 단일 벡터로 변환하지 않는다.

SQLite 원본 + LanceDB 파생 검색 저장소, CPU 필수·GPU 선택, BM25 + RRF, 버전·삭제 상태·색인 세대의 최종 확인은 ADR-002를 유지한다. 기본 모델과 단일 벡터 계약만 이 결정으로 대체한다. PyLate·PLAID를 추가 필수 의존성으로 채택하지 않는다.

이는 초기 구현을 진행할 수 있다는 조건부 채택이다. 모든 OS 호환성이나 운영 품질 완료를 뜻하지 않는다. 지원 OS·아키텍처 요구를 줄이지 않으며 아래 후속 검증이 완료되기 전 전체 지원을 선언하지 않는다.

## 결과와 후속 조치

- 임베딩 프로필·Lance 스키마에 다중 벡터, 차원, MaxSim, 질문 확장·skiplist 규칙을 포함한다. 모델·청크 규칙 변경은 새 프로필로 재색인한다.
- 작은 데이터는 정확 검색으로 시작한다. 최초 ANN 설정은 Recall@5 0.8583으로 사전 기준 0.90에 못 미쳤다. 같은 개발 자료에서 8 probes·refine 10으로 0.9083에 도달한 결과는 독립 검증이나 운영 기본값 보장이 아니다. 실제 규모에서 재평가한다.
- 빈 입력 거부와 64토큰을 넘는 질문의 의미 보존, 512토큰 초과 문서의 청크 보존을 명세·구현한다. 짧은 합성 기록 실험만으로 이를 완료 처리하지 않는다.
- 실제 사용자 기록에 가까운 별도 자료와 장문·혼합 언어 사례를 평가한다. 답 없는 질문은 검색 점수만으로 처리하지 않고 답변 단계의 근거 검증을 시험한다.
- Windows native·macOS·Linux ARM64에서 설치·추론을 검증하고 Intel Mac·Windows ARM 패키지 공백을 해결한다. WSL 실험을 네이티브 지원 증거로 대체하지 않는다.
- 연구의 SQLite 상태 모형과 별도로 제품 outbox·경합·재시작·삭제 후 노출 차단을 검증한다. 연구는 로그인·LangGraph·LLM 답변을 평가하지 않았다.
- KURE-v1/v3·Qwen에 대한 속도·품질 우위를 입증한 것은 아니다. 다른 모델로 전환할 근거가 생기면 공통 평가 자료에서 비교하며 자동 fallback은 하지 않는다.

## 대체 관계

- 대체하는 결정: [ADR-002](ADR-002-local-search-and-embedding.md)의 EmbeddingGemma 2 초기 선택과 단일 768차원 계약. LanceDB·SQLite 역할과 CPU 기본 실행 결정은 유지한다.
- 이 결정을 대체한 기록: 없음.
