import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { ConfirmDialog } from "../src/components/ConfirmDialog";
import { ArcProvider } from "../src/lib/store";
import { installBridge, response, state, visionStatus, voiceStatus } from "./mockBridge";

describe("home screen", () => {
  it("sends a typed command through the bridge and shows the answer", async () => {
    const { api } = installBridge((method, path) =>
      method === "POST" && path === "/api/command"
        ? response({ input: "открой проводник", message: "Открываю проводник.", risk: "A", action: "explorer.open" })
        : undefined,
    );
    render(<App />);
    const input = (await screen.findByTestId("command-input")) as HTMLInputElement;
    await waitFor(() => expect(input.disabled).toBe(false));
    fireEvent.change(input, { target: { value: "открой проводник" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("command-send"));
    });
    await waitFor(() => expect(screen.getByTestId("last-response").textContent).toBe("Открываю проводник."));
    expect(api).toHaveBeenCalledWith("POST", "/api/command", { text: "открой проводник", source: "text" });
  });

  it("voice button toggles push-to-talk", async () => {
    let current = voiceStatus;
    const { api } = installBridge((method, path) => {
      if (method === "POST" && path === "/api/voice/ptt") current = { ...voiceStatus, state: "listening", ptt: true, capturing: true };
      return path.startsWith("/api/voice/ptt") || path === "/api/voice/status" ? current : undefined;
    });
    render(<App />);
    const voice = (await screen.findByTestId("voice-button")) as HTMLButtonElement;
    await waitFor(() => expect(voice.disabled).toBe(false));
    await act(async () => {
      fireEvent.click(voice);
    });
    expect(api).toHaveBeenCalledWith("POST", "/api/voice/ptt", { action: "toggle" });
    await waitFor(() => expect(voice.textContent).toContain("СТОП"));
  });

  it("is honest when the speech model is not installed", async () => {
    installBridge((_m, path) =>
      path === "/api/voice/status" ? { ...voiceStatus, state: "not_installed", message: "Модель распознавания речи не установлена" } : undefined,
    );
    render(<App />);
    const voice = (await screen.findByTestId("voice-button")) as HTMLButtonElement;
    await waitFor(() => expect(screen.getByTestId("voice-note").textContent).toContain("не установлена"));
    expect(voice.disabled).toBe(true);
    expect(screen.getByTestId("status-panel").textContent).toContain("нет модели речи");
  });

  it("downloads a model only after the size is confirmed", async () => {
    const { api } = installBridge();
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-settings"));
    fireEvent.click(await screen.findByTestId("download-whisper-small"));
    expect(api).not.toHaveBeenCalledWith("POST", "/api/voice/models/download", expect.anything());
    expect(screen.getByTestId("confirm-download").textContent).toContain("484 МБ");
    await act(async () => {
      fireEvent.click(screen.getByTestId("confirm-download"));
    });
    expect(api).toHaveBeenCalledWith("POST", "/api/voice/models/download", { id: "whisper-small", confirm: true });
  });

  it("switches LOCAL/ONLINE through settings", async () => {
    const { api } = installBridge();
    render(<App />);
    const toggle = await screen.findByTestId("toggle-mode");
    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/settings", { network: { mode: "ONLINE" } });
  });

  it("shows a banner and disables input when the backend is down", async () => {
    const { bridge } = installBridge();
    bridge.backendStatus = async () => ({ state: "failed", message: "Ядро аварийно завершилось", restarts: 5 });
    render(<App />);
    expect((await screen.findByTestId("backend-banner")).textContent).toContain("Ядро аварийно завершилось");
    expect((screen.getByTestId("command-input") as HTMLInputElement).disabled).toBe(true);
  });
});

describe("confirmation dialog", () => {
  const base = { id: "c1", action: "power.shutdown", title: "Выключение компьютера", description: "выключение через 60 с",
                 expires_at: Date.now() / 1000 + 60 };

  it("critical action needs the acknowledgement checkbox", async () => {
    const { api } = installBridge((_method, path) => (path === "/api/confirm" ? response({ status: "dry_run" }) : undefined));
    render(<ArcProvider><ConfirmDialog info={{ ...base, risk: "C", requires_acknowledge: true }} /></ArcProvider>);
    const approve = screen.getByTestId("confirm-approve") as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("confirm-ack"));
    expect(approve.disabled).toBe(false);
    await act(async () => {
      fireEvent.click(approve);
    });
    expect(api).toHaveBeenCalledWith("POST", "/api/confirm", { id: "c1", approve: true, acknowledge: true });
  });

  it("category B can be approved directly", () => {
    installBridge();
    render(<ArcProvider><ConfirmDialog info={{ ...base, risk: "B", requires_acknowledge: false }} /></ArcProvider>);
    expect((screen.getByTestId("confirm-approve") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("confirm-ack")).toBeNull();
  });
});

describe("gestures", () => {
  it("a gesture asking to switch the view toggles the window, once", async () => {
    let polls = 0;
    const { bridge } = installBridge((_m, path) => {
      if (path !== "/api/vision/status") return undefined;
      polls += 1;
      const events = polls > 1
        ? [{ id: 7, gesture: "index_up", title: "Указательный палец вверх", ts: 1, action: "ui.toggle_compact",
             status: "done", message: "Переключение вида интерфейса", ui: "toggle_compact" }]
        : [];
      return { ...visionStatus, state: "running", running: true, events };
    });
    render(<App />);
    await waitFor(() => expect(bridge.window).toHaveBeenCalledWith("compact"), { timeout: 3000 });
    await new Promise((r) => setTimeout(r, 600));
    expect((bridge.window as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(1);
    expect(screen.getByTestId("gesture-name")).toBeTruthy();
  });

  it("binding a gesture saves only through settings", async () => {
    const { api } = installBridge();
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-settings"));
    const select = (await screen.findByTestId("binding-fist")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).not.toContain("power.shutdown");
    await act(async () => {
      fireEvent.change(select, { target: { value: "window.minimize_all" } });
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/settings", { vision: { bindings: expect.objectContaining({
      fist: { enabled: true, action: "window.minimize_all", params: {} } }) } });
  });
});

describe("local AI", () => {
  it("marks answers proposed by the local model and shows rejected proposals", async () => {
    installBridge((method, path) =>
      method === "POST" && path === "/api/command"
        ? response({ input: "хочу записать мысль", message: "Запускаю «Блокнот».", intent: "ai.plan",
                     data: { ai: true, model: "qwen2.5:7b", rejected: ["system.run: нет в списке разрешённых"] } })
        : undefined,
    );
    render(<App />);
    const input = (await screen.findByTestId("command-input")) as HTMLInputElement;
    await waitFor(() => expect(input.disabled).toBe(false));
    fireEvent.change(input, { target: { value: "хочу записать мысль" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("command-send"));
    });
    const terminal = await screen.findByTestId("terminal");
    await waitFor(() => expect(terminal.textContent).toContain("ИИ"));
    expect(terminal.textContent).toContain("Отклонено: system.run");
  });
});


describe("stage 5: online and documents", () => {
  it("shows search results as links that open through the backend", async () => {
    const research = {
      query: "кубит", summary: "", summary_note: "", errors: [], providers: ["wikipedia"], elapsed_s: 0.4,
      results: [{ title: "Кубит", url: "https://ru.wikipedia.org/wiki/Кубит", snippet: "Единица информации", provider: "wikipedia" }],
    };
    const { api } = installBridge((method, path) => {
      if (method === "POST" && path === "/api/command")
        return response({ input: "найди в интернете кубит", message: "Нашёл 1.", action: "web.research", data: { research } });
      if (method === "POST" && path === "/api/open-url") return response({ message: "Открываю" });
      return undefined;
    });
    render(<App />);
    const input = (await screen.findByTestId("command-input")) as HTMLInputElement;
    await waitFor(() => expect(input.disabled).toBe(false));
    fireEvent.change(input, { target: { value: "найди в интернете кубит" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("command-send"));
    });
    const results = await screen.findByTestId("research-results");
    expect(results.textContent).toContain("ru.wikipedia.org");
    await act(async () => {
      fireEvent.click(screen.getByText("Кубит"));
    });
    expect(api).toHaveBeenCalledWith("POST", "/api/open-url", { url: "https://ru.wikipedia.org/wiki/Кубит" });
  });

  it("marks ONLINE mode with a banner and returns to LOCAL in one click", async () => {
    const { api } = installBridge((_m, path) =>
      path === "/api/state" ? { ...state, mode: "ONLINE", online_active: 1 } : undefined,
    );
    render(<App />);
    const banner = await screen.findByTestId("online-banner");
    expect(banner.textContent).toContain("Идёт запрос");
    expect(screen.getByTestId("mode-indicator").textContent).toContain("сеть");
    await act(async () => {
      fireEvent.click(screen.getByTestId("back-to-local"));
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/settings", { network: { mode: "LOCAL" } });
  });

  it("creates a document from the documents screen; web facts need ONLINE", async () => {
    const { api } = installBridge((method, path) =>
      method === "POST" && path === "/api/documents" ? response({ status: "needs_confirmation", risk: "B" }) : undefined,
    );
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-documents"));
    await waitFor(() => expect(screen.getByTestId("doc-folder").textContent).toContain("Documents"));
    const web = screen.getByTestId("doc-web") as HTMLInputElement;
    expect(web.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("doc-kind"), { target: { value: "xlsx" } });
    fireEvent.change(screen.getByTestId("doc-topic"), { target: { value: "Курсы валют" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("doc-create"));
    });
    expect(api).toHaveBeenCalledWith("POST", "/api/documents", { kind: "xlsx", topic: "Курсы валют", use_web: false });
  });

  it("stores an API key without ever showing it again", async () => {
    const { api } = installBridge((method, path) =>
      method === "PUT" && path === "/api/online/keys/brave" ? { ok: true, provider: "brave", has_key: true } : undefined,
    );
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-settings"));
    const key = (await screen.findByTestId("key-brave")) as HTMLInputElement;
    expect(key.type).toBe("password");
    fireEvent.change(key, { target: { value: "secret-key-123" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Сохранить"));
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/online/keys/brave", { key: "secret-key-123" });
    await waitFor(() => expect(key.value).toBe(""));
  });
});

describe("stage 6: modules", () => {
  const plugin = {
    id: "quiet-hours", name: "Тихие часы", version: "1.0.0", author: "Автор", description: "Вечер", homepage: "",
    permissions: ["volume", "windows"], granted: [], enabled: false, trust: "trusted" as const, signer: "Автор",
    key_id: "0123456789abcdef", blocked: "", commands: [{ phrases: ["вечерний режим"], actions: ["volume.set"], reply: "" }],
  };
  const view = { plugins: [plugin], trusted_keys: [], allow_unsigned: false, errors: [], requestable: ["volume"] };

  it("installs a module from a picked file and grants permissions one by one", async () => {
    const { api, bridge } = installBridge((_method, path, body) => {
      if (path === "/api/plugins") return { ...view, plugins: [] };
      if (path === "/api/plugins/import") return { ...view, installed: "quiet-hours" };
      if (path === "/api/plugins/quiet-hours/grants") return { ...view, plugins: [{ ...plugin, granted: body.modules }] };
      return undefined;
    });
    bridge.pickFile = vi.fn(async () => "C:\\Users\\u\\Downloads\\quiet.arcplugin");
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-plugins"));
    await act(async () => {
      fireEvent.click(await screen.findByTestId("plugin-install"));
    });
    expect(bridge.pickFile).toHaveBeenCalledWith("plugin");
    expect(api).toHaveBeenCalledWith("POST", "/api/plugins/import", { path: "C:\\Users\\u\\Downloads\\quiet.arcplugin" });
    await act(async () => {
      fireEvent.click(await screen.findByTestId("grant-quiet-hours-volume"));
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/plugins/quiet-hours/grants", { modules: ["volume"] });
  });

  it("asks before allowing unsigned modules", async () => {
    const { api } = installBridge((_m, path) => (path === "/api/plugins" ? view : undefined));
    render(<App />);
    fireEvent.click(await screen.findByTestId("nav-plugins"));
    fireEvent.click(await screen.findByTestId("allow-unsigned"));
    expect(api).not.toHaveBeenCalledWith("PUT", "/api/settings", expect.anything());
    await act(async () => {
      fireEvent.click(await screen.findByTestId("allow-unsigned-confirm"));
    });
    expect(api).toHaveBeenCalledWith("PUT", "/api/settings", { plugins: { allow_unsigned: true } });
  });
});
