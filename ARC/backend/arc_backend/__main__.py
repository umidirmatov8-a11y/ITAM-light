"""Backend entry point.

Started by Electron:  arc-backend --parent-pid <pid>   (token in ARC_API_TOKEN)
Prints one JSON line {"event": "ready", "port": N} to stdout when listening on 127.0.0.1.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import logging.handlers
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil


def _setup_logging(log_dir: Path, verbose: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(log_dir / "backend.log", maxBytes=2_000_000, backupCount=3,
                                                   encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    if sys.stderr:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(fmt)
        stream.setLevel(logging.WARNING)
        root.addHandler(stream)


def _watch_parent(pid: int, on_exit, interval: float = 1.5) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval)
            if not psutil.pid_exists(pid):
                logging.getLogger("arc").warning("parent process %s is gone, shutting down", pid)
                on_exit()
                return
    threading.Thread(target=loop, name="parent-watchdog", daemon=True).start()


def _voice_libs() -> dict:
    """The frozen EXE must contain the speech stack (models themselves are downloaded later)."""
    result: dict = {}
    for name in ("numpy", "ctranslate2", "faster_whisper", "sounddevice"):
        try:
            module = importlib.import_module(name)
            result[name] = getattr(module, "__version__", "ok")
        except Exception as exc:  # sounddevice raises OSError when PortAudio is missing (Linux CI)
            result[name] = f"error: {type(exc).__name__}: {exc}"
    required = ["numpy", "ctranslate2", "faster_whisper"] + (["sounddevice"] if sys.platform == "win32" else [])
    result["ok"] = all(not str(result[n]).startswith("error") for n in required)
    return result


def selftest(out: str | None) -> int:
    """Runs core scenarios against a temporary database with the mock controller."""
    from .automation.controller import MockController
    from .models import Status
    from .services import Services

    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        services = Services.create(Path(tmp), controller=MockController(), folders=lambda: {"desktop": tmp})
        try:
            checks = [
                ("открой блокнот", Status.DONE),
                ("АРК, сколько свободного места на диске?", Status.DONE),
                ("увеличь громкость на двадцать процентов", Status.DONE),
                ("выключи компьютер", Status.NEEDS_CONFIRMATION),
                ("абракадабра", Status.UNKNOWN),
                ("найди в интернете погоду", Status.DENIED),
            ]
            for text, expected in checks:
                response = services.assistant.handle_text(text)
                results.append({"input": text, "status": response.status.value, "expected": expected.value,
                                "ok": response.status == expected, "message": response.message})
        finally:
            services.close()
    libs = _voice_libs()
    passed = all(r["ok"] for r in results) and libs["ok"]
    report = json.dumps({"passed": passed, "results": results, "voice_libs": libs}, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(report, encoding="utf-8")
    else:
        sys.stdout.buffer.write(report.encode("utf-8") + b"\n")
    return 0 if passed else 1


def transcribe_file(wav_path: str, model_dir: str) -> int:
    """Diagnostics: `arc-backend --transcribe file.wav --model-dir <models>/whisper-small`."""
    import wave

    import numpy as np

    from .voice.audio import resample
    from .voice.stt import WhisperRecognizer

    with wave.open(wav_path, "rb") as wf:
        if wf.getsampwidth() != 2:
            print(json.dumps({"error": "only 16-bit PCM WAV is supported"}))
            return 2
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        if wf.getnchannels() > 1:
            audio = audio.reshape(-1, wf.getnchannels())[:, 0]
        audio = resample(audio, wf.getframerate())
    recognizer = WhisperRecognizer(Path(model_dir), "auto")
    result = recognizer.transcribe(audio)
    payload = {"text": result.text, "confidence": round(result.confidence, 3), "device": recognizer.device,
               "elapsed_s": round(result.elapsed_s, 2)}
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
    return 0 if result.text else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arc-backend")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--data-dir", type=str, default="")
    parser.add_argument("--mock", action="store_true", help="simulate all system actions")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--selftest-out", type=str, default="")
    parser.add_argument("--transcribe", type=str, default="", help="recognize a WAV file and print JSON")
    parser.add_argument("--model-dir", type=str, default="", help="Whisper model directory for --transcribe")
    args = parser.parse_args(argv)

    if args.transcribe:
        return transcribe_file(args.transcribe, args.model_dir)

    if args.selftest:
        return selftest(args.selftest_out or None)

    token = os.environ.pop("ARC_API_TOKEN", "")
    if len(token) < 32:
        print(json.dumps({"event": "error", "message": "ARC_API_TOKEN is missing"}), flush=True)
        return 2
    if args.data_dir:
        os.environ["ARC_DATA_DIR"] = args.data_dir

    from . import paths
    _setup_logging(paths.logs_dir(), args.verbose)
    log = logging.getLogger("arc")

    import uvicorn

    from .api.server import create_app
    from .automation.controller import create_controller
    from .services import Services

    services = Services.create(controller=create_controller(force_mock=args.mock))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(128)  # accept connections (queued) before announcing readiness
    port = sock.getsockname()[1]

    server_ref: dict = {}

    def request_exit() -> None:
        server = server_ref.get("server")
        if server is not None:
            server.should_exit = True

    app = create_app(services, token, on_shutdown=request_exit)
    config = uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off", timeout_graceful_shutdown=3)
    server = uvicorn.Server(config)
    server_ref["server"] = server
    if args.parent_pid:
        _watch_parent(args.parent_pid, request_exit)
    print(json.dumps({"event": "ready", "port": port, "pid": os.getpid()}), flush=True)
    log.info("listening on 127.0.0.1:%s", port)
    try:
        server.run(sockets=[sock])
    finally:
        services.close()
        log.info("backend stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
