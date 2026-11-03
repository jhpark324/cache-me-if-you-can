// 이 파일의 모든 기록은 화면 디자인 검토용 목데이터입니다.
export const kinds = {
  knowledge: { label: '지식·이해', color: '#83e5be' },
  procedure: { label: '방법·문제 해결', color: '#83e5be' },
  context: { label: '배경·선호', color: '#8cbbf7' },
  episode: { label: '사건·경험', color: '#b5a1f6' },
  reflection: { label: '감정·회고', color: '#b5a1f6' },
  idea: { label: '아이디어', color: '#e7bb72' },
  decision: { label: '결정', color: '#8cbbf7' },
  plan: { label: '계획', color: '#e7bb72' },
  artifact: { label: '재사용 자료', color: '#b3c5cd' },
};

export const records = [
  {
    id: 'brain', title: '나의 세컨드 브레인', kind: 'idea', topic: '지식 관리', date: '2026.11.02',
    excerpt: '흩어진 메모가 연결되면, 다음 생각을 시작할 수 있다.',
    paragraphs: ['AI와 나눈 대화에서 오래 기억하고 싶은 내용만 골라 남기는 공간을 만들고 싶다. 대화 전체보다는 다시 읽을 수 있는 정리본이 필요하다.', '기록을 많이 모으는 것보다, 지금의 질문과 관련 있는 기록을 다시 발견하는 것이 중요하다. 각 기록의 연결과 출처를 따라가며 생각을 이어갈 수 있도록 한다.', '학습한 개념, 개인적인 회고, 프로젝트의 결정은 서로 다른 기록이지만 같은 질문의 맥락이 될 수 있다.'], highlightIndex: 1, related: ['connections', 'capture', 'search'],
  },
  {
    id: 'connections', title: '기록은 연결될 때 지식이 된다', kind: 'knowledge', topic: '지식 관리', date: '2026.11.01',
    excerpt: '새로운 메모를 남길 때, 이미 아는 내용과의 연결을 하나 찾는다.',
    paragraphs: ['독서 노트를 다시 읽다가 같은 주제를 다른 표현으로 여러 번 기록했다는 사실을 발견했다. 개별 메모를 잘 정리하는 것만으로는 관계가 드러나지 않았다.', '새로운 지식을 저장할 때 기존 기록과의 연결을 한 가지 남기면, 나중에 다른 질문으로도 그 지식에 접근할 수 있다. 연결은 메모를 다시 발견하는 경로다.', '단순히 비슷한 단어가 있다는 이유로 인과관계를 만들지는 않는다. 어떤 부분에서 연결되는지 짧게 설명한다.'], highlightIndex: 1, related: ['brain', 'zettelkasten', 'retrieval'],
  },
  {
    id: 'zettelkasten', title: '제텔카스텐과 원자적 메모', kind: 'knowledge', topic: '지식 관리', date: '2026.10.29',
    excerpt: '한 메모에는 한 생각을, 생각 사이에는 연결을.',
    paragraphs: ['오늘은 제텔카스텐의 기록 방식에 관해 공부했다. 원자적 메모는 문장을 기계적으로 짧게 나누는 규칙보다는 다시 사용할 수 있는 생각의 단위를 찾는 방식으로 이해했다.', '메모 하나만 읽어도 의미가 통하도록 맥락을 남기고, 관련된 생각은 링크로 연결한다. 너무 잘게 나눠 조건이나 이유를 잃지 않는 것이 중요하다.', '실제 적용할 때는 긴 정리본도 보존하면서, 다시 찾아볼 개념과 근거 구간에 연결을 붙여보기로 했다.'], highlightIndex: 1, related: ['connections', 'chunking'],
  },
  {
    id: 'retrieval', title: '기억하는 것보다 다시 찾는 것', kind: 'reflection', topic: '학습과 성장', date: '2026.10.31',
    excerpt: '모든 내용을 외우려 하기보다, 필요한 순간에 꺼낼 수 있게 남기기.',
    paragraphs: ['공부한 내용을 곧 잊어버린다고 느껴 조급했다. 그런데 이전 메모를 보니 개념 자체를 처음 접했을 때보다 훨씬 쉽게 이해할 수 있었다.', '기록의 목적은 모든 내용을 영원히 기억하는 것이 아니라, 필요할 때 다시 이해할 수 있는 출발점을 만드는 것이라고 생각했다.', '다음 학습에서는 정리의 분량보다 내가 다시 던질 만한 질문을 함께 남겨보려 한다.'], highlightIndex: 1, related: ['learning', 'connections', 'weekly'],
  },
  {
    id: 'learning', title: '설명해 보면 이해가 드러난다', kind: 'procedure', topic: '학습과 성장', date: '2026.10.30',
    excerpt: '개념을 내 말로 설명하고 막히는 부분을 질문으로 남긴다.',
    paragraphs: ['개념을 읽고 바로 정리하면 익숙한 문장을 옮겨 적는 데 그치기 쉬웠다. 책을 잠시 덮고 직접 설명하는 과정을 추가했다.', '먼저 개념을 짧게 설명한다. 설명이 막히는 부분을 표시하고, 그 부분만 다시 찾아본다. 마지막으로 구체적인 예시 한 개를 만든다.', '이 방법이 항상 가장 빠른 공부법이라는 뜻은 아니다. 이번 데이터베이스 학습에서 이해가 부족한 부분을 찾는 데 도움이 되었다.'], highlightIndex: 1, related: ['retrieval', 'questions'],
  },
  {
    id: 'chunking', title: '긴 글을 청크로 나누는 이유', kind: 'knowledge', topic: 'AI와 검색', date: '2026.11.01',
    excerpt: '본문 전체는 보존하고, 검색은 관련된 구간을 찾는다.',
    paragraphs: ['긴 정리본 전체를 하나의 검색 표현으로 만들면 특정 문단에서 설명한 내용을 찾기 어려울 수 있다. 모델이 처리할 수 있는 입력 길이에도 한계가 있다.', '전체 본문은 그대로 저장하고, 의미와 문단의 경계를 고려해 나눈 구간을 검색한다. 관련 구간을 찾은 뒤에는 주변 맥락과 원문을 함께 읽는다.', '청크를 나누는 것은 본문 일부만 저장한다는 뜻이 아니다. 인용된 구간을 원래 저장본에서 확인할 수 있어야 한다.'], highlightIndex: 1, related: ['search', 'zettelkasten', 'context'],
  },
  {
    id: 'search', title: '질문에서 시작하는 지식 탐색', kind: 'decision', topic: '프로젝트', date: '2026.11.02',
    excerpt: '검색 한 번, 답변 하나. 근거는 옆에서 확인한다.',
    paragraphs: ['웹에서 지식을 찾는 화면은 채팅보다 검색에 가깝게 구성하기로 했다. 질문을 입력하면 관련된 저장 기록에서 답변의 근거를 찾는다.', '한 질문에 하나의 답변과 출처 목록을 보여준다. 출처를 누르면 오른쪽 패널에서 해당 저장본과 인용 구간을 확인한다.', '이전 질문과 답변을 다음 요청에 자동으로 이어 붙이지 않는다. 새로운 검색은 독립적인 질문으로 시작한다.'], highlightIndex: 1, related: ['context', 'brain', 'architecture'],
  },
  {
    id: 'context', title: '좋은 답변에는 맥락이 필요하다', kind: 'context', topic: 'AI와 검색', date: '2026.10.30',
    excerpt: '누구의 말인지, 언제 어떤 상황의 이야기인지 함께 남기기.',
    paragraphs: ['같은 문장도 상황에 따라 의미가 달라진다. 발표 자료는 짧게 만들고 싶지만, 새로운 개념을 공부할 때는 구체적인 예시가 많은 설명이 편하다.', '기록을 재사용할 때는 누구에게, 어떤 상황에서 적용되는 내용인지 함께 읽어야 한다. 과거의 일시적인 조건을 모든 상황의 선호로 확대하지 않는다.', 'AI가 제안한 계획과 내가 실제로 선택한 결정도 구분해 남긴다. 제안이 기록돼 있다는 사실만으로 실행하기로 했다고 볼 수 없다.'], highlightIndex: 1, related: ['search', 'learning', 'architecture'],
  },
  {
    id: 'capture', title: '작게 남기는 기록 습관', kind: 'procedure', topic: '일상과 회고', date: '2026.10.28',
    excerpt: '완벽하게 정리하려고 기다리지 않고, 의미 있는 한 문장부터.',
    paragraphs: ['노트를 멋지게 정리하려다 기록 자체를 미루는 경우가 있었다. 기록을 시작하는 기준을 낮춰보기로 했다.', '기억하고 싶은 일 한 가지, 그때의 생각 한 가지를 먼저 남긴다. 제목과 분류는 나중에 정정할 수 있으므로 본문부터 쓴다.', '짧은 메모라도 당시 상황을 알아볼 수 있는 단서를 남긴다. 나중에 주간 회고에서 관련 기록을 연결해 볼 수 있다.'], highlightIndex: 1, related: ['weekly', 'brain', 'walk'],
  },
  {
    id: 'weekly', title: '이번 주, 조금 느리게 가도 괜찮아', kind: 'reflection', topic: '일상과 회고', date: '2026.11.01',
    excerpt: '진도가 느린 날에도 질문이 선명해졌다는 변화가 있었다.',
    paragraphs: ['이번 주에는 계획한 만큼 많은 것을 끝내지 못했다. 처음에는 제대로 나아가고 있지 않다는 생각이 들었다.', '기록을 다시 읽어보니 막연했던 질문이 구체적으로 바뀌어 있었다. 결과물의 수만으로는 드러나지 않는 변화도 있다는 것을 발견했다.', '다음 주에는 끝낸 일뿐 아니라 새롭게 이해한 것과 남아 있는 질문도 함께 돌아보려고 한다.'], highlightIndex: 1, related: ['retrieval', 'walk', 'questions'],
  },
  {
    id: 'walk', title: '산책 중에 떠오른 생각', kind: 'episode', topic: '일상과 회고', date: '2026.10.31',
    excerpt: '책상에서 풀리지 않던 생각이 걸으면서 이어졌다.',
    paragraphs: ['오후에 잠시 동네를 걸었다. 화면을 보고 있을 때는 계속 같은 문제를 맴돌았는데 걷다 보니 이전에 읽은 글이 떠올랐다.', '돌아와서 떠오른 문장을 바로 메모했다. 산책이 언제나 문제를 해결해 주는 것은 아니지만, 오늘은 생각을 바꾸는 계기가 되었다.', '기록의 제목은 나중에 붙였다. 상황과 느낌이 남아 있으니 다시 읽었을 때 어떤 맥락이었는지 떠올릴 수 있었다.'], highlightIndex: 1, related: ['capture', 'weekly'],
  },
  {
    id: 'architecture', title: '로컬 우선으로 시작하는 이유', kind: 'decision', topic: '프로젝트', date: '2026.11.01',
    excerpt: '내 기록을 내 기기에서 쌓고, 작은 사용 흐름부터 완성한다.',
    paragraphs: ['처음부터 공유와 동기화를 모두 구현하기보다 개인의 저장·조회·정정 흐름을 먼저 완성하기로 했다.', '기록의 정본은 로컬에 보관하고 검색에 필요한 표현은 다시 만들 수 있는 파생 데이터로 구분한다. 기록을 수정했을 때 답변의 근거도 함께 갱신돼야 한다.', '다른 사람과의 공유는 이후에 검토한다. 지금은 내 지식을 안정적으로 다시 읽을 수 있는 경험에 집중한다.'], highlightIndex: 1, related: ['search', 'brain', 'experiment'],
  },
  {
    id: 'experiment', title: '작은 실험으로 가설을 확인하기', kind: 'plan', topic: '프로젝트', date: '2026.10.29',
    excerpt: '먼저 한 흐름을 만들어 보고, 실제로 불편한 곳을 찾는다.',
    paragraphs: ['기획 문서만으로 사용 경험을 모두 알 수는 없다. 작은 시제품으로 핵심 흐름부터 확인해 보려 한다.', '기록 한 개를 저장하고, 질문으로 다시 찾고, 출처를 읽어 정정하는 흐름을 먼저 만든다. 이 과정에서 무엇이 어렵고 무엇이 빠져 있는지 기록한다.', '이 메모는 계획이며 실험을 완료했다는 기록은 아니다. 확인한 결과는 이후 별도로 남긴다.'], highlightIndex: 1, related: ['architecture', 'search', 'questions'],
  },
  {
    id: 'questions', title: '좋은 질문을 남기는 템플릿', kind: 'artifact', topic: '학습과 성장', date: '2026.10.27',
    excerpt: '무엇을 아는지, 무엇이 헷갈리는지, 어떤 예시가 필요한지.',
    paragraphs: ['다시 공부할 때 사용할 질문 템플릿을 정리했다. 모든 칸을 채우기보다 지금 막힌 부분을 명확히 쓰는 데 활용한다.', '지금 이해한 것: …\n설명하기 어려운 부분: …\n확인하고 싶은 구체적 예시: …\n관련해서 이미 남긴 기록: …', '답변을 받으면 원래 질문과 비교해 무엇이 풀렸고 무엇이 남았는지 확인한다. 이 템플릿 자체가 질문의 답을 대신하지는 않는다.'], highlightIndex: 1, related: ['learning', 'retrieval', 'experiment'],
  },
  {
    id: 'serendipity', title: '서로 다른 생각이 만나는 순간', kind: 'idea', topic: '지식 관리', date: '2026.10.30',
    excerpt: '학습 노트와 일상 메모 사이에도 뜻밖의 연결이 있을까?',
    paragraphs: ['학습한 개념만 모아두는 공간과 일상 메모를 완전히 분리하면 서로 다른 종류의 생각이 만날 기회가 줄어들 수 있다.', '같은 질문에 연결되는 기록을 유형에 상관없이 함께 살펴보는 화면을 상상했다. 지식, 회고, 아이디어가 한 장소에서 만나는 것이다.', '단순히 비슷해 보이는 기록을 자동으로 같은 사실로 합치지는 않는다. 연결된 이유와 원래 내용은 각각 확인할 수 있어야 한다.'], highlightIndex: 1, related: ['connections', 'weekly', 'brain'],
  },
  {
    id: 'attention', title: '집중이 잘 되는 나의 조건', kind: 'context', topic: '일상과 회고', date: '2026.10.28',
    excerpt: '오전에는 어려운 개념을, 저녁에는 가벼운 정리를.',
    paragraphs: ['최근 며칠의 기록을 보니 오전에는 새로운 내용을 공부하고 저녁에는 이미 공부한 내용을 정리하는 편이 편했다.', '이것은 최근 학습 상황에 대한 관찰이다. 모든 날이나 모든 업무에서 동일하게 적용되는 고정된 특성으로 단정하지 않는다.', '상황이 바뀌면 이 메모도 다시 확인한다. 어떤 조건에서 그런 느낌이었는지 함께 남기는 것이 더 도움이 된다.'], highlightIndex: 1, related: ['learning', 'weekly', 'capture'],
  },
].map(record => ({ ...record, key: record.kind, revision: 1, visibility: 'public' }));

// 고정된 시작 배치는 프리뷰마다 동일합니다. 사용자는 드래그·회전·확대할 수 있습니다.
const positioned = [
  ['brain', 0, 4, 60, 9],
  ['connections', -195, 110, 12, 6], ['zettelkasten', -360, 210, -15, 4],
  ['retrieval', -82, 218, 20, 4], ['learning', -255, -35, 10, 5],
  ['chunking', 170, 214, -20, 5], ['search', 270, 78, 22, 6],
  ['context', 410, 191, -25, 4], ['capture', -154, -164, 15, 5],
  ['weekly', 60, -194, 30, 6], ['walk', -335, -240, -20, 4],
  ['architecture', 338, -102, 20, 5], ['experiment', 205, -268, -10, 4],
  ['questions', -359, 69, -8, 4], ['serendipity', 45, 128, 22, 5],
  ['attention', -68, -292, -20, 4],
];
const snippets = [
  ['메모 사이의 연결', 'connections', -292, 149, -40], ['다시 발견하는 경로', 'connections', -130, 122, -14],
  ['한 메모, 한 생각', 'zettelkasten', -421, 145, -35], ['의미를 잃지 않기', 'zettelkasten', -261, 261, -50],
  ['내 말로 설명하기', 'learning', -299, -109, -10], ['구체적인 예시', 'learning', -420, -35, -50],
  ['이해의 출발점', 'retrieval', -90, 292, -60], ['남아 있는 질문', 'retrieval', 10, 249, -20],
  ['본문은 그대로', 'chunking', 260, 278, -50], ['문단과 의미 경계', 'chunking', 310, 209, -35],
  ['관련 구간 찾기', 'chunking', 112, 290, -30], ['질문 하나, 답변 하나', 'search', 414, 74, -40],
  ['출처를 함께 읽기', 'search', 157, 53, 4], ['상황별로 다른 선호', 'context', 454, 268, -55],
  ['제안과 선택의 구분', 'context', 465, -5, -30], ['한 문장부터', 'capture', -234, -205, -40],
  ['완벽하지 않아도', 'capture', -108, -93, -8], ['질문이 선명해졌다', 'weekly', 101, -98, -5],
  ['생각을 바꾸는 시간', 'walk', -438, -185, -45], ['맥락을 남기는 습관', 'walk', -261, -304, -55],
  ['로컬에 쌓는 지식', 'architecture', 444, -159, -55], ['정본과 검색의 분리', 'architecture', 273, -177, -35],
  ['한 흐름부터 만들기', 'experiment', 362, -275, -40], ['검증한 것만 기록', 'experiment', 126, -333, -60],
  ['모르는 부분 표시', 'questions', -452, 52, -60], ['뜻밖의 연결', 'serendipity', 57, 63, -40],
  ['최근의 관찰', 'attention', 13, -321, -45], ['조건을 함께 기록', 'attention', -150, -341, -60],
];

const byId = new Map(records.map(r => [r.id, r]));
export const graphNodes = [
  ...positioned.map(([id, x, y, z, size]) => ({ id, recordId: id, title: byId.get(id).title, kind: byId.get(id).kind, x, y, z, size, prominent: true })),
  ...snippets.map(([title, recordId, x, y, z], i) => ({ id: `detail-${i + 1}`, recordId, title, kind: byId.get(recordId).kind, x, y, z, size: 2.5, prominent: false })),
];

const linkPairs = [
  ...records.filter(r => r.id !== 'brain').map(r => ['brain', r.id]),
  ...snippets.map((item, i) => [item[1], `detail-${i + 1}`]),
  ['connections', 'zettelkasten'], ['connections', 'retrieval'], ['connections', 'serendipity'],
  ['learning', 'retrieval'], ['learning', 'questions'], ['learning', 'attention'],
  ['chunking', 'search'], ['chunking', 'context'], ['search', 'architecture'],
  ['search', 'context'], ['capture', 'walk'], ['capture', 'weekly'],
  ['weekly', 'retrieval'], ['weekly', 'serendipity'], ['weekly', 'attention'],
  ['architecture', 'experiment'], ['questions', 'experiment'], ['zettelkasten', 'chunking'],
  ['detail-2', 'detail-26'], ['detail-17', 'detail-18'], ['detail-11', 'detail-13'],
];
export const graphLinks = linkPairs.map(([source, target], i) => ({ id: `connection-${i + 1}`, source, target }));
