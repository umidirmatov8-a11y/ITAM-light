"""Real Windows API checks (run on the Windows CI runner). Nothing destructive is executed."""
import os
import sys
import time

import psutil
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture
def win():
    from arc_backend.automation.controller import WindowsController
    return WindowsController()


def test_launch_exe_detached_and_terminate(win):
    pid = win.launch_exe(sys.executable, ["-c", "import time; time.sleep(30)"], None)
    try:
        assert psutil.pid_exists(pid)
        name = os.path.basename(sys.executable)
        assert pid in win.find_processes(name)
    finally:
        win.terminate_process(pid)
    time.sleep(0.5)
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


def test_launch_missing_exe_reports_error(win):
    from arc_backend.automation.controller import ControllerError
    with pytest.raises(ControllerError):
        win.launch_exe(r"C:\definitely\missing\app.exe", [], None)


def test_windowed_pids_and_volume_do_not_crash(win):
    assert isinstance(win.windowed_pids(), set)
    level = win.volume_get()  # None on machines without an audio device
    assert level is None or 0 <= level <= 100
    assert win.mute_get() in (None, True, False)


def test_known_folders_resolved():
    from arc_backend import paths
    folders = paths.known_folders()
    assert os.path.isdir(folders["desktop"]) or os.path.isdir(folders["documents"])


def test_start_menu_discovery_runs():
    from arc_backend.apps.discovery import scan_shortcuts, start_menu_dirs, scan_uwp
    items = scan_shortcuts(start_menu_dirs())
    assert isinstance(items, list)
    assert isinstance(scan_uwp(), list)
