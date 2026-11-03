export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public retryable = false,
  ) {
    super(message);
  }
}
type Envelope<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      error: { code: string; message: string; retryable?: boolean };
    };
let csrfPromise: Promise<string> | undefined;
function csrf(): Promise<string> {
  if (!csrfPromise)
    csrfPromise = fetch("/api/v1/session", { credentials: "same-origin" })
      .then(async (r) => unwrap<{ csrf_token: string }>(await r.json()))
      .then((x) => x.csrf_token)
      .catch((e) => {
        csrfPromise = undefined;
        throw e;
      });
  return csrfPromise;
}
export function unwrap<T>(value: Envelope<T>): T {
  if (!value.ok)
    throw new ApiError(
      value.error?.code || "SERVER_ERROR",
      value.error?.message || "요청을 처리하지 못했습니다.",
      !!value.error?.retryable,
    );
  return value.data;
}
export async function request(
  path: string,
  init: RequestInit = {},
  sessionRetried = false,
): Promise<Response> {
  const sessionPromise = csrf();
  const csrfToken = await sessionPromise;
  const method = init.method || "GET";
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) headers.set("X-CSRF-Token", csrfToken);
  const result = await fetch("/api/v1" + path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!result.ok) {
    let body;
    try {
      body = await result.json();
    } catch {
      throw new ApiError("HTTP_ERROR", "서버에 연결할 수 없습니다.", true);
    }
    if (
      !sessionRetried &&
      ["SESSION_REQUIRED", "CSRF_REQUIRED"].includes(body?.error?.code)
    ) {
      if (csrfPromise === sessionPromise) csrfPromise = undefined;
      return request(path, init, true);
    }
    unwrap(body);
    throw new ApiError("HTTP_ERROR", "요청을 처리하지 못했습니다.", true);
  }
  return result;
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return unwrap<T>(await (await request(path, init)).json());
}
export const post = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body), signal });
export const uid = () => crypto.randomUUID();
export function errorText(error: unknown) {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      VERSION_CONFLICT:
        "다른 곳에서 수정한 기록입니다. 최신 내용을 다시 연 뒤 수정해 주세요.",
      NOT_FOUND: "더 이상 조회할 수 없는 기록입니다.",
      CONFIRMATION_EXPIRED: "삭제 확인 시간이 지났습니다. 다시 확인해 주세요.",
      INDEX_NOT_READY: "설정에서 검색 모델을 준비한 뒤 다시 검색해 주세요.",
      QUERY_TOO_LONG: "검색어가 너무 깁니다. 짧게 나누어 검색해 주세요.",
      AUTH_REQUIRED: "AI 답변을 사용하려면 설정에서 ChatGPT에 로그인해 주세요.",
      AUTH_NOT_CONFIGURED: "ChatGPT 로그인 연결이 아직 설정되지 않았습니다.",
      MODEL_NOT_READY: "AI 모델 연결을 먼저 확인해 주세요.",
    };
    return messages[error.code] || error.message;
  }
  return error instanceof TypeError
    ? "서버와 연결되지 않았습니다. 서버 실행 상태를 확인해 주세요."
    : error instanceof Error
      ? error.message
      : "요청을 처리하지 못했습니다.";
}
export async function streamQuestion(
  body: unknown,
  signal: AbortSignal,
  onEvent: (event: string, data: unknown) => void,
) {
  const response = await request("/questions", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    onEvent("answer", unwrap(await response.json()));
    return;
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("응답 스트림을 열 수 없습니다.");
  const decoder = new TextDecoder();
  let buffer = "";
  function dispatch(block: string) {
    let event = "message";
    const lines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) lines.push(line.slice(5).trimStart());
    }
    if (lines.length) {
      const raw = JSON.parse(lines.join("\n"));
      onEvent(
        event,
        raw && typeof raw === "object" && "ok" in raw ? unwrap(raw) : raw,
      );
    }
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // Normalize the accumulated buffer, retaining a trailing CR until the
      // next chunk determines whether it starts a CRLF pair.
      const trailingCR = !done && buffer.endsWith("\r");
      if (trailingCR) buffer = buffer.slice(0, -1);
      buffer = buffer.replace(/\r\n|\r/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        dispatch(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
      if (trailingCR) buffer += "\r";
      if (done) {
        if (buffer.trim()) dispatch(buffer);
        break;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
