# 그래프 시안의 제품 맥락

> 폐기된 디자인 시안의 당시 맥락이다. 새 디자인의 제품 지침으로 읽지 않는다. 현재 제품은 [제품 기획](../../project/product-brief.md), 라이브러리 채택은 [ADR-004](../../decisions/ADR-004-graph-visualization-library.md)를 따른다.

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

AI 대화에서 정리한 학습·일상과 감정·메모를 쌓고, 연결된 지식과 저장 내용을 다시 찾으려는 개인 사용자.

## Product Purpose

당시 사용자가 지식 계층을 목데이터로 확인했던 로컬 웹 시안이다. 이후 시안 디자인은 폐기됐고 라이브러리만 ADR-004로 채택됐다.

## Capabilities and Constraints

- 기존 설계: Capture → Revision → 선택적 Node, 여러 기록이 공유하는 Concept, 근거를 가진 Relation.
- 이번 화면: 사용자가 요청한 3D 주제·기록 그래프, 검색·필터·주변 연결 탐색, 상세 패널. 일정 관리 제외.
- 원문 대화는 저장·표시하지 않는다. 현재 저장본과 수정 이력을 구별한다.
- visibility는 public/private, 기본 public. public은 공개 가능 표시이며 실제 인터넷 공개가 아니다.
- 현재 소유자 화면에서는 private 기록도 보인다. 샘플 private 값은 사용자가 지정한 사례를 모사하며 유형별 자동 비공개 규칙이 아니다.
- 고정 합성 데이터. 백엔드·로그인·LLM·임베딩·영구 저장 없음.

## Operating Context

기존 로컬 프로젝트 안에서 브라우저로 검토한다. 다운로드한 라이브러리는 로컬에 포함한다. Windows·macOS·Linux 지원은 제품 목표이며 이번 검증으로 보장하지 않는다.

## Evidence on Hand

[지식 계층](../../architecture/knowledge-layer.md), [기록과 공개 범위](../../project/record-and-visibility.md). 실제 사용자 기록·브랜드·확정 UI는 제공되지 않았다. 색상·배치·예시는 시안의 제안이다.
