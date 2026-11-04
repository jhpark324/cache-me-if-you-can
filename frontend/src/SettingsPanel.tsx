import { useEffect, useRef, useState } from "react";
import { Button, Dialog } from "@radix-ui/themes";
import { ArrowDownToLine, LogIn, LogOut, RefreshCw, X } from "lucide-react";
import { api, post, request, errorText } from "./api";
import type { Settings } from "./types";
import { Tool, ErrorMessage, Loading } from "./ui";

const effortLabels: Record<string, string> = {
  none: "없음",
  minimal: "최소",
  low: "낮음",
  medium: "보통",
  high: "높음",
  xhigh: "매우 높음",
  max: "최대",
};

export default function SettingsPanel({
  onClose,
  onToast,
}: {
  onClose: () => void;
  onToast: (message: string) => void;
}) {
  const [settings, setSettings] = useState<Settings | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [modelsLoading, setModelsLoading] = useState(false),
    [modelsError, setModelsError] = useState(""),
    [busy, setBusy] = useState("");
  const mounted = useRef(false);
  const loadVersion = useRef(0);
  const loadController = useRef<AbortController | null>(null);
  const modelsController = useRef<AbortController | null>(null);
  const actionController = useRef<AbortController | null>(null);
  const requestedAccount = useRef<string | null>(null);
  const busyRef = useRef(false);
  async function load(quiet = false) {
    if (!mounted.current) return null;
    const version = ++loadVersion.current;
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    if (!quiet) setLoading(true);
    if (!quiet) setError("");
    try {
      const next = await api<Settings>("/settings", {
        signal: controller.signal,
      });
      if (version === loadVersion.current && mounted.current) {
        setSettings(next);
        return next;
      }
    } catch (e) {
      if (!controller.signal.aborted && version === loadVersion.current)
        setError(errorText(e));
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
    return null;
  }
  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      loadVersion.current++;
      loadController.current?.abort();
      modelsController.current?.abort();
      actionController.current?.abort();
    };
  }, []);
  async function refreshModels() {
    modelsController.current?.abort();
    const controller = new AbortController();
    modelsController.current = controller;
    setModelsLoading(true);
    setModelsError("");
    try {
      await api("/auth/models", { signal: controller.signal });
      if (controller.signal.aborted || !mounted.current) return;
      const next = await load(true);
      if (!next && !controller.signal.aborted && mounted.current)
        setModelsError("모델 목록을 확인하지 못했습니다. 다시 불러와 주세요.");
    } catch (e) {
      if (!controller.signal.aborted && mounted.current)
        setModelsError(errorText(e));
    } finally {
      if (modelsController.current === controller) {
        modelsController.current = null;
        if (mounted.current) setModelsLoading(false);
      }
    }
  }
  useEffect(() => {
    const auth = settings?.auth;
    if (!auth?.connected || auth.plan_enabled === false) {
      requestedAccount.current = null;
      return;
    }
    const account = auth.active_account_id || auth.email || "connected";
    if (requestedAccount.current === account) return;
    requestedAccount.current = account;
    setModelsError("");
    if (!auth.models?.length) void refreshModels();
  }, [settings?.auth]);
  useEffect(() => {
    if (
      settings?.index?.status !== "preparing" &&
      !(settings?.index?.ready && settings.index.index_counts?.pending)
    )
      return;
    const timer = setInterval(() => {
      if (!busyRef.current && !modelsController.current) void load(true);
    }, 3000);
    return () => clearInterval(timer);
  }, [
    settings?.index?.status,
    settings?.index?.ready,
    settings?.index?.index_counts?.pending,
  ]);
  async function action(name: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    loadVersion.current++;
    loadController.current?.abort();
    modelsController.current?.abort();
    modelsController.current = null;
    setModelsLoading(false);
    const controller = new AbortController();
    actionController.current = controller;
    setBusy(name);
    setError("");
    try {
      if (name === "prepare") {
        await post("/index/prepare", {}, controller.signal);
        if (controller.signal.aborted) return;
        onToast("검색 기능 준비를 시작했습니다.");
        await load(true);
      } else if (name === "login" || name === "change-account") {
        const r = await post<{ authorization_url: string }>(
          "/auth/login",
          name === "change-account" ? { replace_account: true } : {},
          controller.signal,
        );
        if (!controller.signal.aborted) location.assign(r.authorization_url);
      } else if (name === "cancel-login") {
        const result = await post<{ cancelled: boolean }>(
          "/auth/cancel",
          {},
          controller.signal,
        );
        if (controller.signal.aborted) return;
        onToast(
          result.cancelled
            ? "진행 중인 로그인을 취소했습니다."
            : "진행 중인 로그인이 없습니다.",
        );
        await load(true);
      } else if (name === "logout") {
        const result = await post<{ remote_revocation_confirmed: boolean }>(
          "/auth/logout",
          {},
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setModelsError("");
        await load(true);
        if (result.remote_revocation_confirmed === false && mounted.current)
          setError(
            "이 앱의 연결은 해제했지만 ChatGPT에서 해제를 확인하지 못했습니다. ChatGPT 설정에서 앱 연결을 확인해 주세요.",
          );
      } else if (name === "retry") {
        const result = await post<{ retried: number }>(
          "/index/retry",
          {},
          controller.signal,
        );
        if (controller.signal.aborted) return;
        onToast(
          result.retried > 0
            ? `${result.retried}개 기록의 검색 준비를 다시 시작했습니다.`
            : "다시 준비할 기록이 없습니다.",
        );
        await load(true);
      } else if (name === "backup") {
        const response = await request("/backups", {
          method: "POST",
          body: "{}",
          signal: controller.signal,
        });
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `second-brain-${new Date().toISOString().slice(0, 10)}.zip`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        onToast("백업 파일을 다운로드했습니다.");
      }
    } catch (e) {
      if (!controller.signal.aborted && mounted.current) setError(errorText(e));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy("");
    }
  }
  async function saveModel(model: string, reasoningEffort: string | null) {
    if (busyRef.current) return;
    busyRef.current = true;
    loadVersion.current++;
    loadController.current?.abort();
    const controller = new AbortController();
    actionController.current = controller;
    setBusy("model");
    setError("");
    try {
      await api("/settings", {
        method: "PATCH",
        body: JSON.stringify({ model, reasoning_effort: reasoningEffort }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) await load(true);
    } catch (e) {
      if (!controller.signal.aborted && mounted.current) setError(errorText(e));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy("");
    }
  }
  const auth = settings?.auth;
  const models = auth?.models || [];
  const selectedModel = models.find(
    (model) => model.slug === auth?.selected_model,
  );
  const efforts = selectedModel?.supported_reasoning_efforts || [];
  const selectedEffort = efforts.some(
    (item) => item.effort === auth?.selected_reasoning_effort,
  )
    ? auth?.selected_reasoning_effort || ""
    : "";
  const canLoadModels = auth?.connected && auth.plan_enabled !== false;
  const indexStatus =
    (
      {
        uninitialized: "검색 준비가 필요해요",
        not_prepared: "검색 준비가 필요해요",
        not_ready: "검색 준비가 필요해요",
        pending: "검색 준비가 필요해요",
        unloaded: "검색 준비가 필요해요",
        preparing: "검색 기능을 준비하고 있어요",
        ready: "검색 사용 가능",
        failed: "검색 기능을 준비하지 못했어요",
      } as Record<string, string>
    )[settings?.index?.status || ""] || "검색 준비 상태 확인 필요";
  return (
    <>
      <div className="panel-heading">
        <Dialog.Title data-settings-heading tabIndex={-1}>
          설정
        </Dialog.Title>
        <Tool label="설정 닫기" onClick={onClose}>
          <X />
        </Tool>
      </div>
      <ErrorMessage error={error} />
      {loading ? (
        <Loading text="상태를 확인하는 중" />
      ) : (
        settings && (
          <>
            <section className="settings-section">
              <h3>AI 연결</h3>
              <p className="muted">
                ChatGPT 계정으로 저장한 지식에 질문하세요.
              </p>
              <div className="setting-row">
                <span className="settings-account">
                  {settings.auth?.connected
                    ? settings.auth.email || "로그인됨"
                    : "로그인 필요"}
                </span>
                <Button
                  variant="soft"
                  disabled={Boolean(busy)}
                  onClick={() =>
                    void action(settings.auth?.connected ? "logout" : "login")
                  }
                >
                  {settings.auth?.connected ? (
                    <>
                      <LogOut />
                      로그아웃
                    </>
                  ) : (
                    <>
                      <LogIn />
                      Continue with ChatGPT
                    </>
                  )}
                </Button>
              </div>
              {(settings.auth?.connected ||
                settings.auth?.active_account_id) && (
                <Button
                  variant="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void action("change-account")}
                >
                  {settings.auth.connected ? "계정 변경" : "다른 계정으로 연결"}
                </Button>
              )}
              {settings.auth?.pending_login && (
                <div className="concept-status notice">
                  <span>ChatGPT 로그인을 기다리고 있어요.</span>
                  <Button
                    variant="soft"
                    disabled={Boolean(busy)}
                    onClick={() => void action("cancel-login")}
                  >
                    로그인 취소
                  </Button>
                </div>
              )}
              {settings.auth?.error && (
                <p className="notice">{settings.auth.error}</p>
              )}
              {settings.auth?.connected &&
                settings.auth.plan_enabled === false && (
                  <p className="notice">
                    이 계정의 AI 이용 가능 여부를 확인해 주세요.
                  </p>
                )}
              <label className="field">
                답변 모델
                <select
                  value={
                    settings.auth?.connected
                      ? settings.auth.selected_model || ""
                      : ""
                  }
                  disabled={
                    Boolean(busy) ||
                    modelsLoading ||
                    !canLoadModels ||
                    !models.length
                  }
                  aria-describedby="model-help"
                  onChange={(e) => void saveModel(e.target.value, null)}
                >
                  <option value="" disabled>
                    {!settings.auth?.connected
                      ? "로그인 후 선택할 수 있어요"
                      : modelsLoading
                        ? "모델 목록 불러오는 중…"
                        : !models.length
                          ? "선택할 수 있는 모델이 없어요"
                          : "모델을 선택하세요"}
                  </option>
                  {settings.auth?.connected &&
                    settings.auth.selected_model &&
                    !selectedModel && (
                      <option value={settings.auth.selected_model} disabled>
                        {settings.auth.selected_model}
                      </option>
                    )}
                  {models.map((model) => (
                    <option value={model.slug} key={model.slug}>
                      {model.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <p id="model-help" className="muted" role="status">
                {!settings.auth?.connected
                  ? "ChatGPT에 로그인하면 사용할 수 있는 모델을 불러옵니다."
                  : modelsLoading
                    ? "계정에서 사용할 수 있는 모델을 불러오고 있어요."
                    : modelsError
                      ? "모델 목록을 불러오지 못했습니다. 다시 불러와 주세요."
                      : !models.length && canLoadModels
                        ? "이 계정에서 선택할 수 있는 모델이 없습니다. 계정의 AI 이용 권한을 확인하거나 목록을 다시 불러와 주세요."
                        : selectedModel
                          ? "선택한 모델로 질문에 답하고 기록의 주제를 정리합니다."
                          : models.length
                            ? settings.auth?.selected_model
                              ? "이전에 선택한 모델을 사용할 수 없습니다. 다른 모델을 선택해 주세요."
                              : "질문에 답할 모델을 선택해 주세요."
                            : "ChatGPT에서 이 앱의 AI 이용 권한을 확인해 주세요."}
              </p>
              {canLoadModels && modelsError && (
                <ErrorMessage error={modelsError} />
              )}
              {canLoadModels && (
                <Button
                  variant="ghost"
                  disabled={Boolean(busy) || modelsLoading}
                  onClick={() => void refreshModels()}
                >
                  <RefreshCw />
                  {modelsLoading
                    ? "모델 목록 불러오는 중…"
                    : modelsError || !models.length
                      ? "모델 목록 다시 불러오기"
                      : "모델 목록 새로고침"}
                </Button>
              )}
              {settings.auth?.connected &&
                selectedModel &&
                (efforts.length ? (
                  <>
                    <label className="field">
                      추론 수준
                      <select
                        value={selectedEffort}
                        disabled={
                          Boolean(busy) || modelsLoading || !canLoadModels
                        }
                        aria-describedby="reasoning-help"
                        onChange={(e) =>
                          void saveModel(
                            selectedModel.slug,
                            e.target.value || null,
                          )
                        }
                      >
                        <option value="">자동 (모델 기본값)</option>
                        {efforts.map((item) => (
                          <option key={item.effort} value={item.effort}>
                            {effortLabels[item.effort] || item.effort}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p id="reasoning-help" className="muted">
                      답변을 만들 때 얼마나 깊이 생각할지 정합니다. 높을수록
                      응답이 오래 걸릴 수 있어요.
                      {selectedModel.default_reasoning_effort &&
                        ` 기본값: ${effortLabels[selectedModel.default_reasoning_effort] || selectedModel.default_reasoning_effort}.`}
                    </p>
                  </>
                ) : (
                  <p className="muted">
                    이 모델은 선택할 수 있는 추론 수준을 제공하지 않습니다.
                    모델의 기본 설정을 사용합니다.
                  </p>
                ))}
            </section>
            <section className="settings-section">
              <h3>검색 준비</h3>
              <p className="muted">
                저장한 기록을 검색할 수 있도록 준비합니다. 원문은 그대로
                유지됩니다.
              </p>
              <div className="setting-row">
                <span>{indexStatus}</span>
                {(!settings.index?.ready ||
                  (settings.index.index_counts?.failed ?? 0) > 0) && (
                  <Button
                    variant="soft"
                    disabled={
                      Boolean(busy) || settings.index?.status === "preparing"
                    }
                    onClick={() =>
                      void action(settings.index?.ready ? "retry" : "prepare")
                    }
                  >
                    <RefreshCw />
                    {settings.index?.status === "preparing"
                      ? "검색 준비 중…"
                      : settings.index?.ready
                        ? "검색 준비 다시 시도"
                        : "검색 기능 준비"}
                  </Button>
                )}
              </div>
              {!settings.index?.ready && (
                <p className="muted">
                  첫 실행에 검색 모델을 내려받습니다. 준비 중에도 기록을 저장할
                  수 있어요.
                </p>
              )}
              {settings.index?.index_counts && (
                <p className="muted">
                  검색 가능 {settings.index.index_counts.ready}개 · 준비 대기{" "}
                  {settings.index.index_counts.pending}개 · 준비 실패{" "}
                  {settings.index.index_counts.failed}개
                </p>
              )}
              {settings.index?.error_code && (
                <p className="notice">
                  검색 기능을 준비하지 못했습니다. 연결 상태를 확인한 뒤 다시
                  시도해 주세요.
                </p>
              )}
            </section>
            <section className="settings-section">
              <h3>내 데이터</h3>
              <p className="data-path">{settings.data_dir || "로컬 저장소"}</p>
              <p className="muted">
                백업에는 삭제 표시된 내부 기록도 포함됩니다. 로그인 정보와 검색
                준비 데이터는 제외합니다.
              </p>
              <Button
                variant="soft"
                disabled={Boolean(busy)}
                onClick={() => void action("backup")}
              >
                <ArrowDownToLine />
                {busy === "backup" ? "백업 생성 중…" : "백업 다운로드"}
              </Button>
            </section>
          </>
        )
      )}
      {!loading && error && !settings && (
        <Button variant="soft" onClick={() => void load()}>
          다시 확인
        </Button>
      )}
    </>
  );
}
