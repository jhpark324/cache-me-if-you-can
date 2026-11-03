# 로컬 검색과 임베딩

- 상태: LanceDB·KURE-v2 CPU 제품 구현과 WSL 검증 완료. 실제 사용자 품질·전체 OS·규모 확대 평가는 남음
- 확인일: 2026-11-02
- 관련 문서: [지식 계층](knowledge-layer.md), [기술 스택](technology-stack.md), [ADR-002](../decisions/ADR-002-local-search-and-embedding.md), [ADR-003](../decisions/ADR-003-kure-v2-embedding.md)

## 선정 결과

검색 저장소는 LanceDB OSS, 한국어 중심 MVP의 임베딩은 `nlpai-lab/KURE-v2` + Sentence Transformers `MultiVectorEncoder`를 기준으로 개발한다. GPU는 선택 사항이며 CPU float32를 기본으로 한다. 기존 EmbeddingGemma 2 초기 선택과 KURE-v1 우선 비교 추천을 갱신한다.

KURE-v2는 문서마다 단일 벡터를 만드는 모델이 아니다. 토큰별 128차원 벡터를 저장하고 MaxSim으로 비교한다. WSL CPU에서 실제 로딩·인코딩·정확 검색·ICU FTS·RRF·IVF_PQ를 연결했다. [실험 보고서](../research/kure-v2-feasibility/report.md)

조건부 채택은 개발 기준에 대한 결정이다. 실제 사용자 기록의 품질, 긴 질문과 장문 청크 처리, 전체 앱 정합성, Windows·macOS·Linux 배포는 아직 검증을 완료하지 않았다. 지원 요구를 축소하지 않으며 다른 모델 대비 우위도 이번 실험으로 입증하지 않는다.

기록·버전·주제·관계·삭제 표시는 SQLite + WAL에 둔다. LanceDB는 정리본의 검색용 청크와 벡터를 보관하는 파생 저장소다. 두 저장소의 갱신은 하나의 트랜잭션이 아니므로 재시도 가능한 색인 작업과 조회 시 원본 확인을 설계한다.

## 저장소와 실행 책임

| 구성 | 책임 |
| --- | --- |
| SQLite | 정리본과 변경 이력, 현재 상태, 주제·관계, 색인 작업과 활성 임베딩 프로필 |
| LanceDB OSS | 검색용 청크·메타데이터, 토큰별 다중 벡터 MaxSim·BM25와 순위 결합 |
| 임베딩 어댑터 | 질문·문서 입력 계약, 모델 로딩·CPU 추론, 마스킹·정규화·가변 길이×128 검증 |
| 공통 지식 서비스 | 검색 후보의 현재 버전·삭제 여부·파생 출처 확인, 유효한 저장본 반환 |
| LangGraph | 질문 해석·필요한 검색·추가 조회·근거 확인·답변 생성 흐름 제어 |

LanceDB는 로컬 디렉터리에 embedded 방식으로 연결한다. 별도 DB 서버를 추가하지 않으며 각 OS의 사용자 데이터 경로에 SQLite와 Lance 데이터를 둔다. Windows·macOS·Linux에서 직접 실행하는 것이 요구사항이며 WSL은 선택 사항이다. 네이티브 패키지·CPU 명령어·파일 I/O와 미해결 아키텍처는 [운영체제 지원 설계](platform-support.md)를 따른다. [LanceDB 시작하기](https://docs.lancedb.com/quickstart)

## 임베딩 후보 비교

공식 사양과 이번 선정 판단을 구분한다. 아래 모델을 모두 같은 PC에서 비교 실행한 것은 아니다.

| 모델 | 구성과 출력 | 현재 판단 |
| --- | --- | --- |
| [KURE-v2](https://huggingface.co/nlpai-lab/KURE-v2) | 약 154M, 토큰별 128차원, 문서 최대 8,192토큰, Apache-2.0 | 조건부 채택. CPU·LanceDB 연결 실험 완료, 다중 벡터 공간·검색 비용을 감수한다. |
| [KURE-v1](https://huggingface.co/nlpai-lab/KURE-v1) | 약 568M, 단일 1,024차원, 최대 8,192토큰, MIT | 단일 벡터 구조가 필요한 경우의 한국어 비교 후보. 자동 fallback 아님. |
| [KURE-v3](https://huggingface.co/nlpai-lab/KURE-v3) | 약 1.1B, 단일 2,048차원 | 더 큰 모델의 CPU 비용을 감수할 근거가 생기면 비교한다. |
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 약 0.6B, 최대 1,024차원, 32K 문맥, Apache-2.0 | 다국어·코드 검색 비교 후보. 현재 한국어 중심 조건의 기본 모델로 선택하지 않는다. |
| [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2) | 텍스트 전용 약 270M, 단일 768차원 | 이전 초기 선택. 이번 한국어 중심 모델 검증과 결정으로 교체했다. |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | 약 0.1B, 단일 384차원, 최대 512토큰, MIT | 자원 예산을 맞추지 못할 때의 경량 비교 후보. |

## 한국어 중심으로 사용할 때의 재검토

사용자가 KURE-v2의 존재를 지적하고 해당 조합의 프로젝트 적합성 검증을 요청했다. KURE-v1만을 우선하던 추천을 재검토했고, 실제 CPU 실험을 거쳐 KURE-v2로 개발 기준을 바꾼다.

| 모델 | MTEB(kor, v2) 검색 9개 과제 평균 nDCG@10 |
| --- | --- |
| KURE-v2 | 0.8160 |
| KURE-v3 | 0.8027 |
| KURE-v1 | 0.7616 |
| Qwen3-Embedding-0.6B | 0.7140 |

위 수치는 제작자가 공개한 동일 평가표이며 우리 제품 실측과 별개다. 한국어·영어 혼합 기록에서 기술 용어·코드 식별자를 제거하지 않는다. [공식 한국어 평가표](https://huggingface.co/nlpai-lab/KURE-v3#evaluation)

별도로 동결한 합성 기록 36개·질문 24개에서 KURE-v2 정확 검색과 RRF 모두 Hit@1·Recall@5 1.000이었다. 1,036개 짧은 합성 문서에서 조정한 ANN+RRF의 질문 인코딩 포함 p95는 약 0.252초, 본 실험 peak RSS는 약 1.92GiB였다. 작은 개발 자료에서 얻은 결과이므로 실사용 품질 보장이나 모든 OS의 성능으로 일반화하지 않는다. [측정 조건·실패·원시 결과](../research/kure-v2-feasibility/report.md)

## 기본 임베딩 계약

| 항목 | 개발 기준 |
| --- | --- |
| 모델 | `nlpai-lab/KURE-v2`, 검증 revision `3431f86d399d666083890dbb882aced6708873bc` |
| 실행기 | Sentence Transformers `MultiVectorEncoder` + PyTorch, CPU float32·SDPA |
| 검증 버전 | sentence-transformers 6.2.0, transformers 5.22.1, torch 2.15.0+cpu, lancedb 0.41.0; WSL 조합이며 다중 OS lockfile 아님 |
| 출력 | `list<fixed_size_list<float32,128>>`; 문서별 유효 토큰 수가 달라진다. 토큰별 L2 정규화 |
| 점수 | cosine MaxSim; 현재 LanceDB 거리는 `질문 벡터 수 − MaxSim` |
| 질문 | `encode_query`; 내부 `[Q] `와 64토큰 query expansion·마스킹 유지, 빈 질문 거부 |
| 문서 | `encode_document`; 내부 `[D] `·문서 구두점 skiplist·padding 제외 유지, 사용자 입력에 접두어 중복 추가 금지 |
| 청크 | `markdown-v1`: 헤더 구간 → 블록/문단 → 문장 → 토큰. 제목·헤더 맥락·마커·특수 토큰 포함 최대 512토큰. 강제 분할에서만 최대 64토큰 겹침; [상세 규칙](ingestion-and-chunking.md#청크의-기준과-예산) |
| 동시 실행 | 모델 한 인스턴스와 제한된 작업자, 문서 배치 4부터 측정; 질문을 대량 색인보다 우선하도록 후속 구현 |

PyLate를 설치하지 않고 실제 인코딩했다. 검증한 Sentence Transformers 버전은 모델 저장 형식을 변환하고 필요한 마스킹·정규화 모듈을 구성한다. 이 경로에 PyLate/PLAID를 추가 런타임으로 넣을 필요는 없다. 더 낮은 라이브러리 버전이나 ONNX 경로의 호환성까지 검증한 것은 아니다. [모델 사용 지침](https://huggingface.co/nlpai-lab/KURE-v2)

모델 라이브러리는 긴 질문을 64토큰으로 자르고 빈 질문에도 벡터를 만든다. 어댑터는 빈 입력을 거부하고 원 질문을 보존해야 한다. 긴 질문은 제약·부정·날짜를 잃지 않는 질의 분해/재작성 계약을 명세화하며, 조용히 잘라 검색하지 않는다. 현재 어댑터는 빈 질문과 64토큰 초과 검색어를 거절하고, 질문 서비스는 원 질문을 보존한 채 검색 질의로 분해하여 미처리 구간을 추적한다. 구현·실제 검증 범위는 [긴 질문·검색 품질](../specs/004-local-runtime/quality-followup.md)을 따른다.

전체 입력이 512토큰 안이면 짧은 기록은 한 청크로 보존한다. 긴 기록은 Markdown 헤더 구간을 우선하고 작은 인접 형제 구간은 예산 안에서 묶는다. 큰 구간만 블록·문장·토큰 순서로 나누며 나머지는 다음 청크에 보존한다. 각 청크는 기록·버전·본문 위치·헤더 경로를 가리킨다. 독립 구간/완결 블록 사이에는 기본 겹침을 두지 않는다. 이번 실험은 짧은 기록만 사용했으며 장문 분할·겹침 보존 검증과 512/1,024 비교는 별도다. 단일 문서 벡터로 평균 내거나 PLAID 압축 수치를 LanceDB 공간 수치로 간주하지 않는다.

임베딩 프로필에는 `model_id`, `model_revision`, 다중 벡터 여부와 토큰 차원, 정규화·거리·MaxSim 방식, 마커/질문 확장/skiplist 버전, 질문·청크 규칙 버전, 추론 정밀도·런타임 버전을 기록한다. 질문과 테이블은 같은 프로필을 사용한다. 모델·프로필 변경 시 새 테이블을 만들고 현재 기록 전체를 재색인한 뒤 활성 프로필을 전환한다. 단일/다중 벡터나 서로 다른 모델 벡터를 한 검색에 섞지 않는다.

## 키워드와 의미 검색

LanceDB의 다중 벡터 MaxSim과 BM25 전문 검색을 결합하고 초기 순위 결합은 기본 RRF를 사용한다. RRF는 두 결과의 순위를 결합하며 MaxSim 자체나 별도 LLM reranker를 뜻하지 않는다. 질문 벡터 행렬과 검색 문자열을 명시적으로 전달한다. MultiVectorEncoder 출력의 2차원 배열을 여러 독립 질문의 배치로 오해하지 않는다. [다중 벡터 검색](https://docs.lancedb.com/search/multivector-search), [Hybrid 검색](https://docs.lancedb.com/search/hybrid-search)

FTS는 ICU 토크나이저, `stem=False`, `remove_stop_words=False`, `ascii_folding=False`를 기준으로 한다. 제품 구현에는 `create_index(config=FTS(...))`를 사용한다. ICU는 한국어 형태소 분석 품질을 보장하지 않으므로 조사·어미·띄어쓰기·짧은 식별자 실패를 평가하고 필요하면 `lindera/ko-dic`을 비교한다. 코드 기호와 정확한 제품 번호는 의미 검색만으로 일치를 보장하지 않는다. [FTS와 토크나이저](https://docs.lancedb.com/search/full-text-search)

날짜·유형·소유자 조건은 vector와 FTS 양쪽에 동일하게 적용한다. 기록 ID 직접 조회와 정확한 개수·날짜 집계는 SQLite에서 처리한다. 본인 검색에는 `private` 기록도 포함한다. 미래 공유 검색 권한은 별도 명세다. 여러 청크가 같은 기록을 가리키면 기록 단위 중복을 제거하면서 근거 위치를 보존한다. [LanceDB 필터](https://docs.lancedb.com/search/filtering)

작은 데이터는 정확 검색으로 시작하되 다중 벡터는 청크 수뿐 아니라 총 토큰 벡터 수로 비용을 판단한다. ANN 활성화 전 정확 검색 대비 회수율·지연·실제 실행 계획·미색인 행 수를 검증한다. 생성 API 성공만으로 ANN이 사용된다고 가정하지 않는다. 새 행을 건너뛰는 `fast_search`는 기본으로 쓰지 않는다. [색인과 유지 관리](https://docs.lancedb.com/indexing/reindexing)

이번 1,036개 개발 자료에서 IVF_PQ(16 partitions·16 sub-vectors·8bit)의 `nprobes=4/refine_factor=5`는 정확 검색 대비 Recall@5 0.8583으로 실패했다. 같은 자료의 8/10 조정 후 0.9083이 됐으나 독립 검증이 아니다. 이를 운영 기본값이나 모든 규모의 보장으로 고정하지 않고 후속 평가 출발점으로 삼는다. 큰 무색인 테이블의 전수 검색으로 임의 fallback하는 정책도 허용 지연을 정한 뒤 명세화한다.

## 저장·정정·삭제의 정합성


1. SQLite 트랜잭션으로 정리본·버전·현재 상태와 색인 작업을 함께 저장한다. 저장 완료 응답은 커밋된 정리본을 반환한다.
2. 단일 색인 writer가 작업을 읽고 현재 기록 상태를 확인한 뒤 청크와 벡터를 만든다. 모델 추론 동안 SQLite 쓰기 트랜잭션을 열어 두지 않는다.
3. 검색 문서 ID를 `capture_id + revision_id + chunk_id + profile_id + index_generation`에서 결정적으로 만든다. 재시도는 같은 키의 `merge_insert`로 처리한다. 일반 `add`가 고유성 제약을 대신한다고 가정하지 않는다. [갱신과 upsert](https://docs.lancedb.com/tables/update)
4. Lance 쓰기 후 SQLite에서 버전·상태·색인 세대가 여전히 같은지 확인하고 해당 세대만 검색 준비 완료로 표시한다. 정정·삭제·공개 범위 변경은 색인 세대를 변경하므로 동일 본문 버전의 상태 변경도 오래된 작업과 구별된다.
5. 모든 검색 경로는 후보를 사용자나 모델에 전달하기 전에 SQLite의 현재 버전·상태·준비된 세대·파생 출처를 확인한다. 본문과 미리보기도 유효한 저장본에서 가져오며 Lance의 오래된 텍스트를 먼저 노출하지 않는다.

두 저장소 사이의 원자적 commit은 가정하지 않는다. Lance 쓰기 직후 프로세스가 종료되어도 작업 재시도로 복구하며, 무효한 과거 세대의 행은 후속 정리한다. 후보가 필터링되어 부족하면 조회 예산 안에서 추가 후보를 가져온다. 재시작 후 테이블 최신 상태를 확인하며 별도 프로세스 writer를 도입하면 읽기 일관성 설정을 다시 설계한다. [읽기 일관성](https://docs.lancedb.com/tables/consistency)

저장 직후에는 목록·상세에서 정리본을 확인할 수 있다. 검색은 비동기 색인 완료 후 준비되며 화면에 준비 중·완료·실패를 구분한다. 색인 실패를 기록 저장 실패로 표현하거나, 정정 전 벡터를 현재 지식처럼 대신 사용하지 않는다.

삭제는 SQLite의 `deleted_at`을 설정하는 soft delete이며, 즉시 모든 제품 조회·검색·질의응답에서 제외한다. 정본·버전·관계는 내부에 보존하며 삭제 기록 조회·복원·자동 삭제·영구 삭제는 제공하지 않는다. 늦은 색인 작업은 `deleted_at`과 현재 세대를 재확인해 삭제된 기록을 다시 게시하거나 검색 준비 완료로 표시하지 못하게 한다. 파생 검색 행을 정리하더라도 원본 기록은 보존한다. Node 검색·출처 재검토·맥락 반환은 [검색·맥락 계약](retrieval-and-context.md)을 따른다.

## 구현 검증과 모델 전환 조건

WSL의 CPU 로딩·짧은 합성 자료·다중 벡터 연결·ANN 탐색 실험은 [보고서](../research/kure-v2-feasibility/report.md)에 기록했다. 앱 기능이나 전체 OS 지원 검증 완료와 구분한다.

- 사용자 기록을 대표하는 별도 평가 자료를 마련한다. 실제 표현 차이·짧은 용어·부정·한영 혼합·장문 청크·시간에 따른 정정을 포함하고, 개발에 사용한 질문과 최종 평가 질문을 분리한다.
- 근거 없는 질문의 답변 거절과 저장 사실/일반 설명 구분을 LangGraph + 실제 모델 응답으로 검증한다. 유사도만으로 답이 있다고 판정하지 않는다.
- 긴 질문·빈 입력·청크 누락 방지와 여러 청크의 부모 기록 묶음을 기능 수용 기준에 넣는다.
- 실제 데이터 규모에서 정확 검색 대비 ANN 회수율, p50/p95, peak RSS, 총 벡터 수와 색인 공간을 기록한다. 모델 변경이 필요하면 KURE-v1 등 대안을 동일 자료에서 공식 규약대로 비교한다.
- Windows·macOS·Linux의 지원 아키텍처별 설치·추론·경로·재시작을 검증한다. Intel Mac·Windows ARM 패키지 문제를 해결하기 전에 전체 지원을 선언하지 않는다.
- 실제 outbox와 writer에서 중복 작업·저장 중 종료·정정과 색인 경합·soft delete·프로필 전환 중 신규 저장을 검증한다. 삭제 기록의 내부 원본 보존과 모든 제품 조회 제외도 확인한다. 실험의 13개 직렬 상태 검사로 이를 대체하지 않는다.
- 모델 전환은 별도 프로필 전체 재색인 후 수행한다. 품질·자원 부족 시 다른 모델로 자동 전환하거나 서로 다른 벡터를 섞지 않는다.
