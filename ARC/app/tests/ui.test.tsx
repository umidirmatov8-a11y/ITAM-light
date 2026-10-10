import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../src/App";
import { ConfirmDialog } from "../src/components/ConfirmDialog";
import { ArcProvider } from "../src/lib/store";
import { installBridge, response, voiceStatus } from "./mockBridge";

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
