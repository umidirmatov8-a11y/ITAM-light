from __future__ import annotations

import socket
from pathlib import Path

import pytest

from arc_backend.apps.registry import AppInput, AppKind, LaunchType
from arc_backend.automation.controller import MockController
from arc_backend.services import Services


@pytest.fixture
def folders(tmp_path: Path) -> dict[str, str]:
    result = {}
    for key in ("desktop", "documents", "downloads", "pictures"):
        path = tmp_path / "home" / key.capitalize()
        path.mkdir(parents=True)
        result[key] = str(path)
    return result


@pytest.fixture
def controller() -> MockController:
    return MockController()


@pytest.fixture
def services(tmp_path: Path, folders, controller) -> Services:
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders)
    yield svc
    svc.close()


@pytest.fixture
def apps(services: Services) -> dict[str, str]:
    """A typical registry: returns name -> id."""
    reg = services.registry
    items = [
        AppInput(name="Telegram", launch_type=LaunchType.EXE, target=r"C:\Users\u\AppData\Roaming\Telegram Desktop\Telegram.exe"),
        AppInput(name="Steam", launch_type=LaunchType.EXE, target=r"C:\Program Files (x86)\Steam\steam.exe"),
        AppInput(name="Cyberpunk 2077", kind=AppKind.GAME, category="Steam", launch_type=LaunchType.PROTOCOL,
                 target="steam://rungameid/1091500", source="steam"),
        AppInput(name="The Witcher 3", kind=AppKind.GAME, category="Steam", launch_type=LaunchType.PROTOCOL,
                 target="steam://rungameid/292030", aliases=["ведьмак"], source="steam"),
        AppInput(name="Google Chrome", launch_type=LaunchType.LNK,
                 target=r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk",
                 process_name="chrome.exe", aliases=["браузер"]),
        AppInput(name="Калькулятор UWP", launch_type=LaunchType.UWP,
                 target="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", aliases=["калькулятор магазина"]),
        AppInput(name="Admin Tool", launch_type=LaunchType.EXE, target=r"C:\Tools\admintool.exe",
                 run_as_admin=True, aliases=["админка"]),
    ]
    return {item.name: reg.add(item).id for item in items}


@pytest.fixture
def no_network(monkeypatch):
    """Fails the test if anything tries to connect outside loopback (offline-first guarantee)."""
    original = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"unexpected network access to {address}")
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    yield
