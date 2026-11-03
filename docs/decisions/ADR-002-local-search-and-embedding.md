# ADR-002: LanceDB와 CPU 기반 로컬 임베딩 채택

- 상태: `accepted`
- 작성일: 2026-11-02
- 관련 기능·설계: [로컬 검색과 임베딩](../architecture/search-and-embedding.md), [기술 스택](../architecture/technology-stack.md), [지식 계층](../architecture/knowledge-layer.md)

후속 결정: 아래 초기 EmbeddingGemma 2 선택과 단일 벡터 계약은 [ADR-003](ADR-003-kure-v2-embedding.md)의 KURE-v2 조건부 채택으로 대체했다. LanceDB·SQLite 역할과 CPU 기본 실행 결정은 유지한다. 아래 본문은 최초 결정의 근거를 보존한다.

## 배경

현재 삭제 정책은 [ADR-006](ADR-006-soft-delete-without-trash.md)을 따른다. 아래 초기 설계의 휴지통·복원·영구 삭제 관련 표현은 당시 검토 이력이며 제품은 soft delete·조회 차단만 제공한다. 저장소·CPU 실행 결정은 유지한다.

한국어 개인 기록의 키워드·의미 검색을 로컬 CPU에서 수행하면서 기록의 버전·삭제·출처 계약을 유지해야 한다. GPU는 선택 사항으로 둔다.

이 결정은 저장소 역할과 CPU 기본 실행의 근거를 보존한다. 최초 모델 선택 당시에는 실제 사용자 자료와 OS별 실행을 검증하지 않았으며, 이후 모델 평가와 선택 변경은 ADR-003에 기록한다.

## 검토한 대안

| 대안 | 장점 | 단점 |
| --- | --- | --- |
| SQLite FTS5 + sqlite-vec | 기록과 검색 데이터를 한 저장소에 모을 수 있다. | 키워드·벡터 검색 조합과 색인 수명 관리를 직접 구성해야 한다. |
| SQLite 기록 + LanceDB 검색 | 기록의 트랜잭션과 검색용 저장·조회 기능을 각각 활용한다. | 두 저장소의 비동기 갱신과 재시도·재검증이 필요하다. |
| LanceDB에 기록과 이력까지 통합 | 저장 기술 종류가 줄어든다. | 현재 관계·버전·삭제 도메인 설계를 다시 검토해야 한다. |
| EmbeddingGemma 2 텍스트 전용 | 약 270M 구성, 다국어, CPU 실행 지침과 768차원 출력 | 한국어 개인 기록 품질과 최신 라이브러리 호환성을 실측해야 한다. |
| KURE-v1 | 한국어 검색 학습·평가 근거와 기존 Sentence Transformers 사용 경로 | 더 큰 모델의 CPU 메모리·지연을 측정해야 한다. |
| multilingual-e5-small | 더 작은 모델과 벡터로 구성할 수 있다. | 한국어 실제 검색 품질과 짧은 문맥의 영향을 비교해야 한다. |

모델 세부 사양과 최신 후보의 공식 출처는 [후보 비교](../architecture/search-and-embedding.md#임베딩-후보-비교)에 기록한다.

## 결정

LanceDB OSS를 로컬 키워드·벡터 검색 저장소로 채택한다. 기록·버전·관계·삭제 상태는 SQLite에 두고 검색 문서와 벡터는 재생성 가능한 파생 데이터로 관리한다. 기존 FTS5·sqlite-vec 추천을 교체한다.

초기 임베딩 모델은 `google/embeddinggemma-2`의 텍스트 전용 구성으로 선정한다. CPU float32·768차원·정규화한 벡터를 기준으로 하며 모델·입력 규약·청크 규칙을 프로필로 고정한다. GPU, 멀티모달 입력, 양자화를 필수 구성으로 추가하지 않는다. [공식 모델 카드](https://huggingface.co/google/embeddinggemma-2)

검색은 dense + BM25와 RRF를 기준으로 설계한다. SQLite에는 기록 변경과 색인 작업을 함께 commit하고, Lance 반영은 재시도 가능한 worker가 수행한다. 검색 결과의 버전·상태는 SQLite에서 최종 확인한다. 구체적인 초기 설정과 검증 조건은 [검색 설계](../architecture/search-and-embedding.md)에 둔다. [LanceDB Hybrid 검색](https://docs.lancedb.com/search/hybrid-search)

## 결과와 후속 조치

- 저장 완료와 검색 준비 완료를 구분하며 정정·삭제된 내용이 늦은 색인 작업으로 다시 노출되지 않게 한다.
- [현재 운영체제 지원 목표](../architecture/platform-support.md)에 따라 Windows·macOS·Linux CPU 환경에서 설치·메모리·지연·한국어 검색 품질을 측정한다. 모델 간 공개 벤치마크를 우리 제품 성능으로 대체하지 않는다.
- KURE-v1은 한국어 비교 후보, E5-small은 자원 절약 비교 후보로 남긴다. 모델 변경은 전체 재색인과 활성 프로필 전환으로 수행한다.
- 물리 삭제·보관 기한·복원은 제공하지 않는다. 삭제 표시는 정본에 보존하고 검색 노출을 차단하며 [현재 삭제 정책](ADR-006-soft-delete-without-trash.md)을 따른다.
- 검색과 무관한 나머지 스택의 추천 상태는 이 결정으로 바뀌지 않는다.

## 대체 관계

- 대체하는 결정: 없음. 기술 스택 문서의 FTS5·sqlite-vec 및 E5-small 기본 추천을 갱신한다.
- 이 결정을 대체한 기록: [ADR-003](ADR-003-kure-v2-embedding.md)이 초기 임베딩 모델·단일 벡터 계약을 대체한다. 삭제 범위는 [제품 기획의 soft delete 정책](../project/product-brief.md#변경과-삭제)로 좁혔다. 나머지 결정은 유효하다.
