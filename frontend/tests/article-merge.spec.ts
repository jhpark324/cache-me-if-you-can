import { expect, test } from "@playwright/test";
import { mergeArticleExcerpt } from "../src/mergeArticleExcerpt";

test("병합 원문의 인용은 대상의 동명 번호를 가리키지 않고 코드 예시는 보존한다", () => {
  const original = [
    "| 근거 | 설명 |",
    "| --- | --- |",
    "| [1](#cite-1) | 문서 |",
    "",
    "같은 근거 [1][paper]. 일반 [링크](https://example.com).",
    "",
    "[paper]: #cite-1",
    "",
    "표기 예시 `[1](#cite-1)`.",
    "",
    "```markdown",
    "[1](#cite-1)",
    "```",
  ].join("\n");
  const target = "대상 글 [1](#cite-1)";
  const merged = target + "\n" + mergeArticleExcerpt(original, original);
  expect(merged).toContain(target);
  expect(merged).toContain("| (원문 출처 1) | 문서 |");
  expect(merged).toContain(
    "같은 근거 (원문 출처 1). 일반 [링크](https://example.com).",
  );
  expect(merged).not.toContain("[paper]: #cite-1");
  expect(merged).toContain("표기 예시 `[1](#cite-1)`.");
  expect(merged).toContain("```markdown\n[1](#cite-1)\n```");
});

test("선택 구간 밖의 정의와 Unicode 구간을 사용해 원래 인용을 식별한다", () => {
  const prefix = "😀 [1](#cite-1)\n\n";
  const excerpt = "다른 근거 [1][original]";
  const original = prefix + excerpt + "\n\n[original]: #cite-1";
  expect(
    mergeArticleExcerpt(original, excerpt, Array.from(prefix).length),
  ).toBe("다른 근거 (원문 출처 1)");
});
