# 운영체제 지원 설계

- 상태: Windows·macOS·Linux 직접 실행은 사용자 확정 요구, WSL CPU에서 임베딩·검색 조합 실행 확인, 네이티브 앱·배포 검증 전
- 확인일: 2026-11-02
- 관련 문서: [제품 기획](../project/product-brief.md), [기술 스택](technology-stack.md), [검색과 임베딩](search-and-embedding.md)

## 지원 목표

Windows·macOS·Linux 각각에서 로컬 FastAPI 서버, SQLite·LanceDB, 임베딩을 CPU로 직접 실행한다. WSL·Docker·GPU는 필수 조건으로 두지 않는다. 자체 웹은 각 OS의 브라우저에서 사용하고 Codex는 로컬 MCP에 연결한다. 모바일 기기 자체에서 서버를 실행하는 요구는 이번 지원 범위에 포함하지 않는다.

이는 지원 요구사항이며 호환성 검증이 끝났다는 선언이 아니다. OS 이름과 CPU 아키텍처를 구분하고, 최소 OS·Python 버전과 설치 방법은 실제 조합 검증 뒤 확정한다. Intel Mac이나 Windows ARM을 사용자 동의 없이 지원 대상에서 제외하지 않는다.

## 현재 배포 패키지 확인

2026-11-02에 확인한 공식 배포 파일 기준이다. `있음`은 해당 플랫폼의 wheel 존재이며 전체 의존성 설치나 앱 실행 성공을 뜻하지 않는다. 이 표는 배포 파일 확인 기록이며 현재 의존성 범위와 고정 버전은 `backend/pyproject.toml`과 `backend/uv.lock`을 따른다.

| 패키지 | Windows x64 | Windows ARM64 | macOS ARM64 | macOS Intel | Linux x64 | Linux ARM64 |
| --- | --- | --- | --- | --- | --- | --- |
| LanceDB 0.41.0 | 있음 | 없음 | 있음 | 없음 | 있음 | 있음 |
| PyArrow 26.0.0 | 있음 | 없음 | 있음 | 있음 | 있음 | 있음 |
| PyTorch 2.15.0 | 있음 | 공식 CPU index에 있음 | 있음 | 없음 | 있음 | 있음 |
| ONNX Runtime 1.31.1 | 있음 | 있음 | 있음 | 없음 | 있음 | 있음 |

출처: [LanceDB 파일](https://pypi.org/project/lancedb/0.41.0/#files), [PyArrow 파일](https://pypi.org/project/pyarrow/26.0.0/#files), [PyTorch CPU index](https://download.pytorch.org/whl/cpu/torch/), [ONNX Runtime 파일](https://pypi.org/project/onnxruntime/1.31.1/#files).

현재 비교한 최신 패키지 조합의 공통 Python 하한은 3.11이며, WSL의 초기 조합 실험은 Python 3.12에서 수행했다. 네이티브 OS별 조합 검증도 Python 3.12를 기준으로 제안한다. 최신 PyTorch wheel 태그는 macOS ARM에서 macOS 14 이상, Linux에서 glibc 2.28 이상을 요구한다. 이 조건을 모든 OS의 모든 버전으로 일반화하지 않는다. [PyTorch 배포 파일](https://pypi.org/project/torch/2.15.0/#files)

LanceDB의 기본 x64 wheel에는 AVX2 등 CPU 명령어 조건도 있다. 구형 CPU에는 공식 `lancedb-compat` 또는 별도 빌드 경로가 있지만, 해당 플랫폼의 배포 파일과 기능을 따로 확인해야 한다. OS가 같아도 모든 CPU에서 실행되는 것으로 간주하지 않는다. [LanceDB 설치 조건](https://pypi.org/project/lancedb/0.41.0/)

## 현재 실행 확인 범위

WSL의 Linux x64 CPU 환경에서 KURE-v2, Sentence Transformers 6.2.0의 `MultiVectorEncoder`, PyTorch 2.15.0, LanceDB 0.41.0 조합을 설치하고 모델 인코딩·다중 벡터 검색·ICU FTS·RRF 하이브리드 검색·ANN 실행을 확인했다. 측정 조건과 결과, 한계는 [KURE-v2 구성 적합성 평가](../research/kure-v2-feasibility/report.md)에 기록한다.

이 결과는 한국어 중심 MVP의 개발 기준으로 이 조합을 조건부 채택하는 근거다. Windows·macOS·Linux 네이티브 실행이나 전체 OS 배포를 승인한 결과는 아니다. FastAPI·웹·MCP·OAuth를 포함한 WSL 로컬 제품 시험은 [004](../specs/004-local-runtime/validation.md)에서 추가 수행했다. Windows·macOS·Linux 네이티브 OS별 설치·실행은 아직 수행하지 않았다. 위 패키지 표는 배포 파일 존재만 나타내며, WSL에서 실행한 조합의 결과를 다른 OS·아키텍처에 확대하지 않는다. Intel Mac과 Windows ARM64의 패키지 제약도 해결되지 않았다.

## 실행·배포 원칙

- 동일 Python 도메인 서비스와 웹 번들을 사용하되 OS·아키텍처별 네이티브 패키지 및 설치 조합을 검증한다. 모든 OS에 같은 바이너리 파일을 배포할 수 있다고 가정하지 않는다.
- 기본 임베딩 경로는 KURE-v2를 Sentence Transformers의 `MultiVectorEncoder`와 PyTorch CPU로 실행하는 구성이다. CUDA·FlashAttention·Apple MPS는 선택 최적화이며 기본 동작의 전제가 아니다.
- 검색 저장소와 모델 실행기는 별도 어댑터로 분리한다. ONNX Runtime은 검증 가능한 대안이지만, ONNX로 바꾼다는 이유만으로 모든 아키텍처 호환성을 보장하지 않는다. Sentence Transformers의 ONNX backend만 선택해도 Torch 설치 의존성이 사라지는 것은 아니다. [Sentence Transformers 패키지](https://pypi.org/pypi/sentence-transformers/6.2.0/json)
- 데이터·모델 캐시는 OS별 사용자 데이터 경로에 두고 경로 구분자·한글·공백을 처리한다. 설치 폴더 쓰기 권한이나 WSL 경로를 전제로 하지 않는다.
- 서버 시작·정상 종료·작업 재개·로컬 브라우저 열기·OAuth callback은 OS별로 검증한다. 서버 자원 정리를 POSIX signal이나 bash 스크립트 하나에만 의존시키지 않는다.

## 미해결 호환성과 대응

Windows x64, Apple Silicon macOS, Linux x64·ARM64는 현재 주요 패키지의 배포 파일이 있어 우선 검증할 수 있다. Intel Mac과 Windows ARM64에는 현재 스택의 설치 경로를 해결할 작업이 남아 있다. 이 차이는 지원 완료나 지원 제외를 뜻하지 않는다.

Intel Mac은 PyTorch가 2.2.x 이후 공식 macOS x64 배포를 중단했다. 이전 버전 고정, 별도 빌드, 다른 임베딩 실행기를 검토할 수 있지만 최신 모델·Lance 기능과 함께 동작하는지는 미검증이다. 구버전 패키지를 설치할 수 있다는 이유만으로 현재 설계의 ICU FTS 등 기능이 그대로 제공된다고 가정하지 않는다. [PyTorch 공식 발표](https://pytorch.org/blog/pytorch2-2/)

Windows ARM64는 PyTorch CPU 배포가 있지만 LanceDB·PyArrow의 해당 버전 wheel이 없다. 필요 시 프로젝트에서 네이티브 의존성을 빌드·배포하는 경로를 검증한다. 검색 저장소 변경이나 다른 런타임 도입이 필요해지면 기존 LanceDB 선택과의 영향을 결정 기록에 남긴다. 사용자의 네이티브 실행 요구를 WSL 필수 설치로 대신 충족했다고 표시하지 않는다.

## 구현 수용 기준으로 옮길 항목

지원 조합마다 아래 항목을 실행하고 OS 버전·CPU 아키텍처·Python·패키지·모델 revision을 함께 기록한다.

1. GPU가 없는 깨끗한 환경에서 설치, 서버 시작, 자체 웹 접근, MCP 연결이 동작한다.
2. 한국어·한영 혼합 기록을 저장·조회·수정하고, 같은 모델 프로필의 유한한 임베딩과 기대 차원을 얻는다. OS별 부동소수점 차이를 비트 단위 동일성으로 요구하지 않는다.
3. 키워드·벡터 검색, 색인 실패 후 재시도, soft delete에서 현재 기록 상태가 유지된다. 삭제된 원본·이력은 내부에 보존하고 모든 제품 조회에서 제외한다. 재시작·재시도로 삭제 상태가 되돌아오지 않아야 한다.
4. 한글·공백 경로, 재시작, 정상 종료와 중단된 작업 복구가 동작한다.
5. 자체 OAuth의 로그인·callback·갱신·스트리밍·취소가 각 OS에서 동작한다.
6. 질문 임베딩과 검색 지연, 초기 모델 로딩, 최대 메모리를 같은 입력 조건에서 측정한다.

현재 패키지 메타데이터 확인과 WSL CPU 환경의 임베딩·검색 실험까지 수행했다. Windows·macOS·Linux 네이티브 환경의 설치·모델 추론·앱 시험과 위 수용 기준 전체 검증은 남아 있다.
