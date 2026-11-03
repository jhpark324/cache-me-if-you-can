# KURE-v2 + LanceDB 적합성 판단

- 실행일: 2026-11-02
- 판정: **한국어 중심 MVP의 개발 기준으로 조건부 채택**. Windows·macOS·Linux 전체 배포 승인이나 실사용 검색 품질 보장은 아니다.
- 결정: [ADR-003](../../decisions/ADR-003-kure-v2-embedding.md)
- 방법과 사전 기준: [실험 프로토콜](index.md)
- 재현 자료: [평가 자료](fixtures.json), [본 실험 코드](run_benchmark.py), [원시 결과](results.json), [보완 검사 코드](check_runtime.py), [보완 결과](runtime-checks.json), [패키지 목록](requirements.txt)

## 판단 근거

KURE-v2를 실제 CPU에서 실행하고 토큰별 벡터를 LanceDB 정확 검색·ICU FTS·RRF 및 IVF_PQ와 연결했다. 한국어 학습, 일상/감정, 짧은 메모를 찾는 소규모 평가를 통과했고, 이 PC에서는 검색 지연과 메모리에 여유가 있었다. 한국어 중심 개발의 기본 모델을 기존 EmbeddingGemma 2에서 KURE-v2로 바꿀 근거는 충분하다.

다만 새 모델을 바로 제품 배포 가능한 상태로 판정하지 않는다. 정답 평가가 작은 합성 자료에 한정되고, ANN은 첫 설정에서 실패해 같은 자료로 조정했으며, 지원 대상 OS에서 앱을 실행한 결과도 아니다. KURE-v1·Qwen 등 다른 모델은 이번에 실행하지 않았으므로 CPU 속도나 실제 품질의 상대 우위를 입증하지 않는다.

## 환경과 고정한 조건

| 항목 | 실제 실행 조건 |
| --- | --- |
| OS·CPU | WSL2 Linux x86_64, i5-10400F 2.90GHz, 6코어/12스레드, AVX2 |
| 메모리 | 시스템 약 15.58GiB; 측정치는 별도 실험 프로세스 기준 |
| Python | 3.12.13 |
| 주요 패키지 | torch 2.15.0+cpu, sentence-transformers 6.2.0, transformers 5.22.1, lancedb 0.41.0, pyarrow 26.0.0 |
| 모델 | `nlpai-lab/KURE-v2`, revision `3431f86d399d666083890dbb882aced6708873bc` |
| 실행 | CPU float32, SDPA, Torch 4스레드·interop 1, 질문 batch 1·문서 batch 4 |
| 출력 | 질문 64×128, 문서 가변 길이×128, 토큰별 L2 정규화 |
| 문서 길이 | 최대 입력 512토큰; 실제 평가 자료는 66~97토큰으로 잘림 없음 |
| 검색 | cosine MaxSim, ICU FTS(`stem=False`, `remove_stop_words=False`, `ascii_folding=False`), 기본 RRF |

PyLate를 설치하지 않고 MultiVectorEncoder로 로딩·추론했다. 이 Sentence Transformers 버전이 모델의 PyLate 저장 형식을 변환하고 마스킹·정규화 모듈을 구성했다. 모델 내부의 `[Q] `·`[D] `를 런타임이 적용하므로 입력에 다시 붙이지 않는다. 모델 카드의 별도 작업 지시문 불필요 설명을 내부 마커가 없다는 뜻으로 해석하지 않는다. [공식 모델 사용법](https://huggingface.co/nlpai-lab/KURE-v2)

질문 확장은 64토큰을 점수 계산에 사용한다. 보완 검사에서 짧은 질문의 attention 대상은 7토큰, 점수 대상은 64토큰임을 확인했다. 문서의 패딩·구두점 제외 규칙은 토큰 ID로 독립 계산한 마스크와 같았으며, 짧은 문서를 단독/긴 문서와 배치로 인코딩했을 때 최대 원소 오차는 `4.17e-7`이었다. 평가 질문 27개는 내부 마커·특수 토큰 포함 15~33토큰이라 잘리지 않았다.

## 작은 한국어 평가

평가 전 자료와 정답을 동결했다. 합성 기록 36개·정답 있는 질문 24개를 세 범주에 균등 배분했고, 의역·부정·정정 전후·계획과 실행·제안과 결정의 혼동 사례를 포함했다. 정답 없는 질문 3개는 아래 지표에 포함하지 않았다. q16은 정답이 두 개이므로 Hit@1은 정답 중 하나를 첫 번째로 찾는 비율이다.

| 검색 방식 | Hit@1 | Recall@5 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| KURE-v2 정확 MaxSim | 1.000 | 1.000 | 1.000 | 1.000 |
| ICU FTS 단독 | 0.750 | 1.000 | 0.875 | 0.908 |
| MaxSim + FTS + RRF | 1.000 | 1.000 | 1.000 | 1.000 |

KURE-v2·RRF는 각 범주의 Hit@1도 1.000이었다. FTS는 학습 0.875·일상 0.750·메모 0.625였다. 예를 들어 최종 독서 모임 시간을 묻는 q21에서 FTS는 이전 제안(m09)을 확정 기록(m10)보다 높게 찾았다. 원자성 설명 q01, 발표 전 걱정 q10, 산책 후 불안 q15, 실제 만든 도구 q20, 실행 전 계획 메모 q24도 FTS 1위 오류였다.

이 결과는 **36개 짧은 합성 기록의 연결 검증**이다. FTS도 모든 정답을 상위 5개에서 찾는 비교적 작은 문제였고, 합성 문장의 표현 방식이 쉬운 단서가 될 수 있다. 100%를 실제 사용자 데이터 정확도로 일반화하거나 공개 대규모 벤치마크와 같은 의미로 표현하지 않는다.

NumPy로 계산한 cosine MaxSim과 LanceDB 정확 검색의 상위 10개 점수가 모든 질문에서 일치했다. 거리 변환은 `_distance = 질문 벡터 수 − MaxSim`이며 최대 절대 오차는 `1.14e-5`였다. 더 작은 거리가 더 좋은 결과다. 단일 벡터 평균 풀링으로 바꾸지 않았다. [LanceDB 다중 벡터 검색](https://docs.lancedb.com/search/multivector-search)

## CPU 시간·메모리·공간

| 항목 | 측정값 | 해석 범위 |
| --- | --- | --- |
| 캐시된 가중치 모델 로딩 | 0.46초 | 다운로드·Python 시작·라이브러리 import 제외; 완전한 cold start 아님 |
| 질문 인코딩 p50 / p95 | 123 / 157ms | 24개 질문, 워밍업 후 batch 1 |
| 36개 정확 검색 p50 / p95 | 19.6 / 21.4ms | 임베딩 계산 제외 |
| 36개 RRF 검색 p50 / p95 | 23.8 / 26.9ms | 임베딩 계산 제외 |
| 36개 인코딩+RRF p95 | 182ms | 별도로 잰 질문별 두 단계 시간의 합 |
| 1,036개 정확 검색 p50 / p95 | 295 / 320ms | 임베딩 계산 제외 |
| 1,036개 조정 후 인코딩→ANN+RRF p50 / p95 | 233 / 252ms | 보완 실행에서 실제 연속 측정; HTTP·SQLite 최종 확인·LLM 응답 제외 |
| 문서 인코딩 | 1,000개 약 113.36초, 약 8.82개/초 | 75~86 입력 토큰의 반복적인 짧은 합성 기록 |
| IVF_PQ 생성 | 6.16초 | 1,036개 문서·74,761개 토큰 벡터 |
| 프로세스 peak RSS | 1.92GiB | 모델·인코딩·DB 작성·색인 전체 본 실험; 앱 전체 메모리 아님 |
| 모델 로드 직후 RSS | 1.11GiB | 다른 패키지와 모델을 포함 |
| 가중치 파일 | 약 292.89MiB | 저장된 가중치; float32 실행 메모리와 다름 |
| 검색 DB 전체 | 38.15MiB | 1,036개, 본문·원벡터·FTS·ANN·메타데이터·해당 테이블 버전 포함 |
| 이 중 ANN 색인 파일 | 약 1.34MiB | 원벡터를 지우지 않으므로 DB 전체 크기와 구분 |

실행 시 다른 프로세스를 모두 중단한 전용 벤치마크 환경은 아니었고 질문을 여러 동시 사용자로 반복 부하 시험하지 않았다. p95는 표본 24개의 분위수이며 지속 부하 SLA가 아니다. 대량 색인 중 질문 우선 처리나 FastAPI 이벤트 루프 비차단은 이번 코드에서 검증하지 않았다.

다중 벡터는 모델 크기가 작아도 저장 공간이 작다고 단정할 수 없다. 이번 문서당 평균은 약 72.2개 벡터이며 원벡터만 약 36.50MiB였다. 512개 벡터를 보관하는 청크 하나는 float32에서 `512 × 128 × 4 = 256KiB`가 필요하다. 공식 모델 카드의 PLAID 압축 수치를 현재 LanceDB DB 크기로 가져오지 않는다.

## ANN 최초 실패와 후속 조정

원래 평가 자료에 서로 다른 텍스트 1,000개를 추가해 실제로 인코딩했다. 복제 벡터를 넣은 실험은 아니지만 제목·번호·날짜·일부 주제를 바꾼 반복 문서이므로 실제 대규모 품질 평가도 아니다. 아래 회수율은 **정답 회수율이 아니라 동일 데이터의 정확 검색 상위 5개와의 평균 일치 비율**이다.

IVF_PQ는 cosine, 16개 partition, 16개 sub-vector, 8bit로 만들었다. 색인 1,036행·미색인 0행과 `ANNSubIndex → MultivectorScoring → KNNVectorDistance` 실행 계획을 확인했다.

| 설정 | 정확 검색 대비 Recall@5 | 검색 p95 | 판정 |
| --- | --- | --- | --- |
| 최초 `nprobes=4`, `refine_factor=5` | 0.8583 | 57ms | 사전 기준 0.90 미달 |
| 후속 `nprobes=8`, `refine_factor=10` | 0.9083 | 83ms | 같은 개발 자료에서 기준 도달 |
| 후속 `nprobes=16`, `refine_factor=20` | 0.9167 | 127ms | 비용 증가 대비 개선 제한적 |

최초 실패를 원시 결과에 보존했다. 후속 두 설정은 결과 확인 후 같은 자료로 탐색한 것이며 독립 holdout 통과가 아니다. 가장 먼저 기준에 도달한 8/10 설정으로 연속 하이브리드 요청을 측정했다. 이 값을 모든 규모의 운영 기본값으로 고정하지 않는다. 데이터가 작을 때는 정확 검색을 사용하고, ANN 활성화 전에 실제 데이터·청크 길이·색인 규모로 회수율과 지연을 검증한다. 전체 partition을 탐색해도 PQ 후보 단계의 누락이 남을 수 있다.

## 정정·삭제와 답 없는 질문

SQLite 메모리 테이블을 현재 상태의 기준으로 삼고 LanceDB에 낡은 후보를 일부러 남겼다. 13개 직렬 검사에서 정정 전 revision, 검색 준비 전 행, 휴지통, 복원 전 generation, 다른 profile, 삭제된 원본, 뒤늦은 색인 행이 최종 후보에서 제외됐다. 본인 `private` 기록은 조회됐고, 표시 본문은 검증된 SQLite 저장본에서 읽었다.

이는 **최종 검증 규칙의 실행 가능한 모형**이다. 앱 구현, 두 DB 경합, outbox 원자성·재시도, 동시 쓰기, 충돌·재시작, 출처가 바뀐 파생 기록, bounded 재조회, 영구 삭제 후 과거 파일 정리까지 검증한 결과가 아니다. 후보를 한 번 넉넉히 읽고 필터링했으므로 실제로 추가 검색을 반복하는 refill 구현 검증도 아니다.

답 없는 질문도 이웃 문서를 반환한다. 특히 “독서 모임 장소를 어디로 예약했어?”는 관련 모임 기록을 높은 순위로 찾지만, 그 기록에는 예약한 장소의 근거가 없다. 유사도만으로 답이 있다고 판단하거나 단일 임계값으로 환각을 방지할 수 있다고 결론 내리지 않는다. LangGraph 답변 단계에서 실제 저장본의 근거 여부를 확인하고, 근거가 없으면 모른다고 답하는 별도 평가가 필요하다. 이번에는 LLM을 호출하지 않았다.

## 입력·배포에서 남은 조건

보완 검사에서 363토큰 질문은 런타임 전처리 후 64토큰이 됐고, 빈 질문도 64×128 벡터로 인코딩됐다. 제품 어댑터는 빈 입력을 거부하고 긴 질문을 조용히 자르지 않아야 한다. 원 질문을 유지하면서 질의를 분해·재작성하는 계약을 별도로 정해야 한다. 장문 청크 분할과 본문 위치·겹침 보존은 아직 구현하지 않았다.

이번 실행은 WSL Linux x86_64 하나뿐이다. Windows native·macOS·Linux ARM64에서 설치·추론·파일 경로·재시작을 확인하지 않았다. Intel Mac의 최신 Torch/LanceDB, Windows ARM의 LanceDB/PyArrow wheel 공백도 남아 있다. 모든 OS 지원 요구를 줄이지 않으며, 배포 조합 해결과 실기 검증 전에는 전체 지원 완료로 표시하지 않는다. [플랫폼별 상태](../../architecture/platform-support.md)

## 사전 기준별 결론

| 기준 | 결과 |
| --- | --- |
| F-01 설치·CPU·출력·마스킹 | 현재 WSL 환경에서 통과. 빈 입력·긴 질문의 제품 계약은 미구현 |
| F-02 정확 MaxSim 연결 | 통과. 거리 오차 `1.14e-5`, 상위 10개 점수 일치 |
| F-03 대표 합성 질의 Recall@5 ≥ 0.85 | 통과 1.000. 실제 사용자 데이터의 품질 증명은 아님 |
| F-04 질문 인코딩+검색 p95 ≤ 2초 | 현재 측정 조건 통과. 연속 ANN+RRF 약 0.252초 |
| F-05 peak RSS ≤ 4GiB | 통과 약 1.92GiB. 전체 앱 자원 예산은 추가 측정 |
| F-06 ANN Recall@5 ≥ 0.90와 실행 계획 | 최초 실패 0.8583; 같은 자료에서 조정 후 0.9083, 독립 재검증 필요 |
| F-07 변경·삭제 경계 | 상태 검증 모형 13개 통과. 실제 앱 통합·경합 검증은 미완료 |

## 재현 방법

이 스크립트는 Linux/WSL 실험용으로 `resource`와 `/proc/cpuinfo`를 사용한다. Windows/macOS 지원 시험용 제품 실행기가 아니다. 가중치·가상환경·DB는 저장소 밖에 두었다. `requirements.txt`는 이 환경의 패키지 스냅샷이며 다중 플랫폼 lockfile이 아니다.

```bash
uv venv --python 3.12 "$HOME/.cache/second-brain/kure-v2-feasibility/venv"
uv pip install --python "$HOME/.cache/second-brain/kure-v2-feasibility/venv/bin/python" --index-url https://download.pytorch.org/whl/cpu torch==2.15.0
uv pip install --python "$HOME/.cache/second-brain/kure-v2-feasibility/venv/bin/python" -r docs/research/kure-v2-feasibility/requirements.txt
```

같은 환경의 Python에서 아래 snapshot을 받은 뒤 프로젝트 루트에서 본 실험, 보완 검사 순으로 실행한다. 본 실험은 저장소 밖에 새로운 시간별 DB 폴더를 만들며 `results.json`과 보완 결과는 실행 때 갱신된다. 비교 실험은 기존 원시 결과를 별도 보관한 뒤 실행한다.

```python
from pathlib import Path
from huggingface_hub import snapshot_download
snapshot_download(
    "nlpai-lab/KURE-v2",
    revision="3431f86d399d666083890dbb882aced6708873bc",
    cache_dir=str(Path.home() / ".cache/second-brain/kure-v2-feasibility/models"),
    allow_patterns=["*.json", "*.safetensors"],
)
```

```bash
"$HOME/.cache/second-brain/kure-v2-feasibility/venv/bin/python" docs/research/kure-v2-feasibility/run_benchmark.py
"$HOME/.cache/second-brain/kure-v2-feasibility/venv/bin/python" docs/research/kure-v2-feasibility/check_runtime.py
```

실행 로그에는 기존 `create_fts_index` 및 score column 자동 포함 API의 deprecated 경고가 있다. 이번 고정 버전에서는 동작했으며 제품 구현에서는 `create_index(config=FTS(...))`와 명시적 score projection을 사용해 다시 검증한다. 로그 원문은 [본 실행](run.log)과 [보완 실행](runtime-checks.log)에 보존했다.
