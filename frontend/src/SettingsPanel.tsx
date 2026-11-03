import { useEffect, useRef, useState } from "react";
import { Button, Dialog } from "@radix-ui/themes";
import { ArrowDownToLine, LogIn, LogOut, RefreshCw, X } from "lucide-react";
import { api, post, request, errorText } from "./api";
import type { Settings } from "./types";
import { Tool, ErrorMessage, Loading } from "./ui";

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
    [busy, setBusy] = useState("");
  const loadVersion = useRef(0);
  const loadController = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  async function load(quiet = false) {
    const version = ++loadVersion.current;
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    if (!quiet) setLoading(true);
    setError("");
    try {
      const next = await api<Settings>("/settings", {
        signal: controller.signal,
      });
      if (version === loadVersion.current) setSettings(next);
    } catch (e) {
      if (!controller.signal.aborted && version === loadVersion.current)
        setError(errorText(e));
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    return () => {
      loadVersion.current++;
      loadController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (settings?.index?.status !== "preparing") return;
    const timer = setInterval(() => {
      if (!busyRef.current) void load(true);
    }, 3000);
    return () => clearInterval(timer);
  }, [settings?.index?.status]);
  async function action(name: string, accountId?: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    loadVersion.current++;
    loadController.current?.abort();
    setBusy(name);
    setError("");
    try {
      if (name === "prepare") {
        await post("/index/prepare", {});
        onToast("검색 모델 준비를 시작했습니다.");
        await load();
      } else if (name === "login") {
        const r = await post<{ authorization_url: string }>(
          "/auth/login",
          accountId ? { account_id: accountId } : {},
        );
        location.assign(r.authorization_url);
      } else if (name === "cancel-login") {
        const result = await post<{ cancelled: boolean }>("/auth/cancel", {});
        onToast(
          result.cancelled
            ? "진행 중인 로그인을 취소했습니다."
            : "진행 중인 로그인이 없습니다.",
        );
        await load();
      } else if (name === "logout") {
        await post("/auth/logout", {});
        await load();
      } else if (name === "models") {
        await api("/auth/models");
        await load();
      } else if (name === "retry") {
        await post("/index/retry", {});
        onToast("검색 준비를 다시 시작했습니다.");
        await load();
      } else if (name === "backup") {
        const response = await request("/backups", {
          method: "POST",
          body: "{}",
        });
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `second-brain-${new Date().toISOString().slice(0, 10)}.zip`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        onToast("백업 파일을 다운로드했습니다.");
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      busyRef.current = false;
      setBusy("");
    }
  }
  const indexStatus =
    (
      {
        uninitialized: "모델 준비 필요",
        not_prepared: "모델 준비 필요",
        not_ready: "모델 준비 필요",
        pending: "모델 준비 필요",
        unloaded: "모델 준비 필요",
        preparing: "모델을 준비하고 있어요",
        ready: "검색 사용 가능",
        failed: "모델 준비 실패",
      } as Record<string, string>
    )[settings?.index?.status || ""] || "검색 모델 준비";
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
                <span>
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
              {settings.auth?.pending_login && (
                <div className="concept-status notice">
                  <span>완료되지 않은 로그인 시도가 있습니다.</span>
                  <Button
                    variant="soft"
                    disabled={Boolean(busy)}
                    onClick={() => void action("cancel-login")}
                  >
                    로그인 시도 취소
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
              {settings.auth?.models?.length ? (
                <label className="field">
                  사용 모델
                  <select
                    value={settings.auth.selected_model || ""}
                    disabled={Boolean(busy)}
                    onChange={async (e) => {
                      if (busyRef.current) return;
                      busyRef.current = true;
                      setBusy("model");
                      loadVersion.current++;
                      loadController.current?.abort();
                      setError("");
                      try {
                        await api("/settings", {
                          method: "PATCH",
                          body: JSON.stringify({ model: e.target.value }),
                        });
                        await load();
                      } catch (err) {
                        setError(errorText(err));
                      } finally {
                        busyRef.current = false;
                        setBusy("");
                      }
                    }}
                  >
                    <option value="" disabled>
                      모델 선택
                    </option>
                    {settings.auth.models.map((model) => (
                      <option value={model.slug} key={model.slug}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {settings.auth?.connected && (
                <Button
                  variant="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void action("models")}
                >
                  <RefreshCw />
                  모델 목록 새로고침
                </Button>
              )}
              {(settings.auth?.accounts?.length || 0) > 1 && (
                <label className="field">
                  연결할 계정
                  <select
                    value={settings.auth?.active_account_id || ""}
                    disabled={Boolean(busy)}
                    onChange={(e) => void action("login", e.target.value)}
                  >
                    {settings.auth?.accounts?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label || a.email || "ChatGPT 계정"}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </section>
            <section className="settings-section">
              <h3>검색 준비</h3>
              <div className="setting-row">
                <span>{indexStatus}</span>
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
                  {settings.index?.ready ? "색인 다시 시도" : "모델 준비"}
                </Button>
              </div>
              {!settings.index?.ready && (
                <p className="muted">
                  첫 실행에 검색 모델을 내려받습니다. 준비 중에도 기록을 저장할
                  수 있어요.
                </p>
              )}
              {settings.index?.index_counts && (
                <p className="muted">
                  준비 {settings.index.index_counts.ready} · 대기{" "}
                  {settings.index.index_counts.pending} · 실패{" "}
                  {settings.index.index_counts.failed}
                </p>
              )}
              {settings.index?.error_code && (
                <p className="notice">
                  검색 모델을 준비하지 못했습니다. 연결 상태를 확인한 뒤 다시
                  시도해 주세요.
                </p>
              )}
            </section>
            <section className="settings-section">
              <h3>내 데이터</h3>
              <p className="data-path">{settings.data_dir || "로컬 저장소"}</p>
              <p className="muted">
                백업에는 삭제 표시된 내부 기록도 포함됩니다. 로그인 정보와 검색
                인덱스는 제외합니다.
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
