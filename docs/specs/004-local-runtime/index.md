# 로컬 제품 런타임

- 상태: `in-progress`
- 범위: 기존 002 기록 서비스와 검색·답변·로그인·MCP·실제 웹·백업 통합
- [명세](spec.md) · [설계](design.md) · [작업](tasks.md) · [검증](validation.md)
- 후속 구현: [Codex 연결](codex-integration.md) · [운영 안정성](operations-followup.md) · [웹 관리](web-management-followup.md) · [검색·응답 품질](quality-followup.md)
- 완료한 개선: [홈 그래프 복원·Cache Me If You Can 이름 적용](home-graph-refresh.md)
- 완료한 개선: [UI·UX 점검과 개선·출처 패널 날짜](ui-ux-refinement.md)
- 체험 데이터: [실제 저장소 테스트 기록](demo-data.md)
- 완료한 개선: [여섯 기록 유형·Codex 저장 시나리오](record-kinds-and-scenarios.md)
- 최종 점검: [리모트 등록 전 통합 검증](final-review.md)
- 최신 점검 완료: [2026-11-03 리모트 재점검·README 보강](prepublish-review-2026-11-03.md)
- 최종 점검 상세: [백엔드](backend-final-review.md) · [웹](frontend-final-review.md)
- 완료한 개선: [ReAct 에이전트·8회 도구 제한·PII](react-agent.md)
- 완료한 개선: [하나의 답변·작은 출처·검색 로딩](answer-reading.md)
- 완료한 개선: [검색 상단 배치와 검색 근거 그래프](retrieval-graph.md)
- 기준: [전체 계획](../../plans/mvp-delivery.md), [서비스 계약](../../architecture/service-contracts.md), [MVP](../../project/mvp-scope.md)

후속 1~4번의 구현과 로컬 검증을 완료했다. 실제 로그인·모델 응답·강제 갱신, Codex 기록 관리와 사용자의 삭제 승인, 웹 병합·관계 편집, 긴 본문·질문 처리와 한국어 평가를 확인했다. 실계정 로그아웃 후 재로그인·네이티브 OS 및 평가 한계는 검증 문서에 구분한다.
