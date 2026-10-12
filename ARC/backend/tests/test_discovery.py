import json
import struct

from arc_backend.apps.discovery import (import_discovered, parse_lnk, parse_start_apps, parse_vdf, scan_epic,
                                        scan_shortcuts, scan_steam)
from arc_backend.apps.matcher import match_app
from arc_backend.apps.registry import AppKind, LaunchType


def make_lnk(target: str, arguments: str = "", unicode_info: bool = False) -> bytes:
    flags = 0x02 | 0x80 | (0x20 if arguments else 0)
    header = struct.pack("<I16sI", 0x4C, b"\x01\x14\x02\x00" + b"\x00" * 4 + b"\xc0" + b"\x00" * 6 + b"\x46", flags)
    header += b"\x00" * (0x4C - len(header))
    volume = struct.pack("<IIII", 0x11, 3, 0x1234, 0x10) + b"\x00"
    if unicode_info:
        header_size = 0x24
        base_ansi = b"\x00"
        base_w = target.encode("utf-16-le") + b"\x00\x00"
        body_offset = header_size
        vol_off = body_offset
        base_off = vol_off + len(volume)
        suffix_off = base_off + len(base_ansi)
        base_w_off = suffix_off + 1
        suffix_w_off = base_w_off + len(base_w)
        body = volume + base_ansi + b"\x00" + base_w + b"\x00\x00"
        info = struct.pack("<IIIIIIIII", header_size + len(body), header_size, 1, vol_off, base_off, 0, suffix_off,
                           base_w_off, suffix_w_off) + body
    else:
        header_size = 0x1C
        base = target.encode("latin-1") + b"\x00"
        vol_off = header_size
        base_off = vol_off + len(volume)
        suffix_off = base_off + len(base)
        body = volume + base + b"\x00"
        info = struct.pack("<IIIIIII", header_size + len(body), header_size, 1, vol_off, base_off, 0, suffix_off) + body
    data = header + info
    if arguments:
        data += struct.pack("<H", len(arguments)) + arguments.encode("utf-16-le")
    return data + b"\x00\x00\x00\x00"


def test_parse_lnk_ansi_and_unicode():
    link = parse_lnk(make_lnk(r"C:\Program Files\Telegram\Telegram.exe", "--minimized"))
    assert link.target == r"C:\Program Files\Telegram\Telegram.exe"
    assert link.arguments == "--minimized"
    link = parse_lnk(make_lnk(r"C:\Игры\Игра.exe", unicode_info=True))
    assert link.target == r"C:\Игры\Игра.exe"


def test_parse_lnk_rejects_garbage():
    import pytest
    with pytest.raises(ValueError):
        parse_lnk(b"MZ" + b"\x00" * 100)


def test_scan_shortcuts(tmp_path):
    programs = tmp_path / "Programs"
    (programs / "Telegram Desktop").mkdir(parents=True)
    (programs / "Telegram Desktop" / "Telegram.lnk").write_bytes(make_lnk(r"C:\T\Telegram.exe"))
    (programs / "Telegram Desktop" / "Uninstall Telegram.lnk").write_bytes(make_lnk(r"C:\T\unins000.exe"))
    (programs / "Manual.lnk").write_bytes(make_lnk(r"C:\T\manual.pdf"))
    (programs / "broken.lnk").write_bytes(b"junk")
    items = scan_shortcuts([programs])
    assert [(i.name, i.process_name, i.category, i.launch_type) for i in items] == [
        ("Telegram", "Telegram.exe", "Telegram Desktop", LaunchType.LNK)]
    assert "телеграм" in items[0].aliases


VDF = '''
"libraryfolders"
{
    "0"
    {
        "path"      "LIBRARY_ROOT"
        "apps" { "1091500" "123" }
    }
}
'''


def test_parse_vdf():
    data = parse_vdf('"AppState" { "appid" "570" "name" "Dota 2" "Nested" { "k" "v\\\\x" } }')
    assert data == {"AppState": {"appid": "570", "name": "Dota 2", "Nested": {"k": "v\\x"}}}


def test_scan_steam(tmp_path):
    root = tmp_path / "Steam"
    lib = tmp_path / "Library2"
    (root / "steamapps").mkdir(parents=True)
    (lib / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(VDF.replace("LIBRARY_ROOT", str(lib).replace("\\", "\\\\")))
    (lib / "steamapps" / "appmanifest_1091500.acf").write_text('"AppState" { "appid" "1091500" "name" "Cyberpunk 2077" }')
    (root / "steamapps" / "appmanifest_228980.acf").write_text('"AppState" { "appid" "228980" "name" "Steamworks Common Redistributables" }')
    (root / "steamapps" / "appmanifest_bad.acf").write_text('"AppState" { "appid" "x; calc" "name" "Bad" }')
    items = scan_steam(root)
    assert [(i.name, i.target, i.kind) for i in items] == [("Cyberpunk 2077", "steam://rungameid/1091500", AppKind.GAME)]
    assert scan_steam(None) == []


def test_scan_epic(tmp_path):
    good = {"DisplayName": "Fortnite", "AppName": "Fortnite", "CatalogNamespace": "fn", "CatalogItemId": "4fe75bbc",
            "LaunchExecutable": "FortniteGame/Binaries/Win64/FortniteLauncher.exe"}
    evil = {**good, "DisplayName": "Evil", "AppName": "x&calc"}
    (tmp_path / "a.item").write_text(json.dumps(good))
    (tmp_path / "b.item").write_text(json.dumps(evil))
    (tmp_path / "c.item").write_text("{broken")
    items = scan_epic(tmp_path)
    assert len(items) == 1
    assert items[0].target == "com.epicgames.launcher://apps/fn%3A4fe75bbc%3AFortnite?action=launch&silent=true"
    assert items[0].process_name == "FortniteLauncher.exe"


def test_parse_start_apps():
    out = json.dumps([{"Name": "Калькулятор", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
                      {"Name": "Bad", "AppID": "not valid id"}])
    items = parse_start_apps(out)
    assert [(i.name, i.launch_type) for i in items] == [("Калькулятор", LaunchType.UWP)]
    single = parse_start_apps(json.dumps({"Name": "Paint", "AppID": "Microsoft.Paint_8wekyb3d8bbwe!App"}))
    assert single[0].name == "Paint"
    assert parse_start_apps("") == [] and parse_start_apps("garbage") == []


def test_import_discovered_deduplicates(services, tmp_path):
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "appmanifest_1.acf").write_text('"AppState" { "appid" "1091500" "name" "Cyberpunk 2077" }')
    items = scan_steam(root)
    report = import_discovered(services.registry, items + items)
    assert report.added == ["Cyberpunk 2077"] and report.skipped == 1
    assert import_discovered(services.registry, items).added == []
    result = match_app("киберпанк", services.registry.list())
    assert result.best and result.best.name == "Cyberpunk 2077"
