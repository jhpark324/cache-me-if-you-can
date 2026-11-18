// The example gives each record a single chunk and orders IDs A, B, C.
const rrfDemo = document.querySelector("[data-rrf-demo]");

function fuseRanks(channels) {
  const scores = new Map();
  for (const channel of channels) {
    channel.forEach((id, index) => {
      const rank = index + 1;
      scores.set(id, (scores.get(id) || 0) + 1 / (60 + rank));
    });
  }
  return Array.from(scores, ([id, score]) => ({ id, score })).sort(
    (left, right) => right.score - left.score || left.id.localeCompare(right.id),
  );
}

function explainWinner(stage, winner, channels) {
  const contributions = channels.map(([name, ids]) => ({
    name,
    rank: ids.indexOf(winner.id) + 1,
  })).filter((item) => item.rank > 0);
  const places = contributions.map((item) => `${item.name} ${item.rank}위`).join("와 ");
  const sum = contributions.map((item) => `1/${60 + item.rank}`).join(" + ");
  return `${stage} 1위 ${winner.id}의 점수는 ${places}에서 온 ${sum} = ${winner.score.toFixed(6)}입니다.`;
}

function showRanks() {
  const ranks = (channel) => Array.from(rrfDemo.querySelector(`[data-rrf-input="${channel}"]`).value);
  const vectors = ranks("vector");
  const lexical = ranks("lexical");
  const body = fuseRanks([vectors, lexical]);
  const bodyOrder = body.map((item) => item.id);
  const topics = ranks("topic");
  const final = topics.length ? fuseRanks([bodyOrder, topics]) : body;

  const resultRows = final.map((record, index) => {
    const row = document.createElement("tr");
    const id = document.createElement("th");
    id.scope = "row";
    id.textContent = record.id;
    row.insertCell().textContent = `${index + 1}위`;
    row.append(id);
    const bodyHit = body.find((item) => item.id === record.id);
    row.insertCell().textContent = bodyHit ? bodyHit.score.toFixed(6) : "없음";
    row.insertCell().textContent = record.score.toFixed(6);
    return row;
  });
  rrfDemo.querySelector("[data-rrf-results]").replaceChildren(...resultRows);

  const bodyExplanation = explainWinner("본문", body[0], [["의미", vectors], ["낱말", lexical]]);
  const finalExplanation = topics.length
    ? explainWinner("최종", final[0], [["본문", bodyOrder], ["주제", topics]])
    : "주제 후보가 없어 이 본문 순위를 최종 순위로 사용합니다.";
  rrfDemo.querySelector("[data-rrf-explanation]").textContent = `${bodyExplanation} ${finalExplanation}`;
}

if (rrfDemo) {
  const controls = rrfDemo.querySelector("[data-rrf-controls]");
  controls.hidden = false;
  controls.addEventListener("change", showRanks);
  showRanks();
}
