"""Static guarantees: no shell execution, no eval/exec, subprocess only with argument lists."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "arc_backend"


def _calls():
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                yield path, node


def _name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return f"{_name(func.value)}.{func.attr}"
    return ""


def test_no_eval_exec_or_os_system():
    banned = {"eval", "exec", "os.system", "os.popen", "compile", "__import__"}
    found = [(p.name, n.lineno, _name(n.func)) for p, n in _calls() if _name(n.func) in banned]
    assert found == []


def test_subprocess_never_uses_shell_and_takes_lists():
    for path, node in _calls():
        name = _name(node.func)
        if name.startswith("subprocess."):
            for kw in node.keywords:
                if kw.arg == "shell":
                    assert isinstance(kw.value, ast.Constant) and kw.value.value is False, (path.name, node.lineno)
            if node.args:
                first = node.args[0]
                # an argument list (literal, variable or list-building helper), never a command string
                assert isinstance(first, (ast.List, ast.Name, ast.Call)), (path.name, node.lineno)
                assert not isinstance(first, (ast.Constant, ast.JoinedStr, ast.BinOp)), (path.name, node.lineno)


def test_powershell_only_with_fixed_command():
    """The only PowerShell call (Get-StartApps) uses a constant command string."""
    for path, node in _calls():
        if _name(node.func) == "subprocess.run" and node.args and isinstance(node.args[0], ast.List):
            items = node.args[0].elts
            if items and isinstance(items[0], ast.Constant) and "powershell" in str(items[0].value).lower():
                assert path.name == "discovery.py"


def test_piper_args_are_a_list():
    from arc_backend.voice.tts import PiperSynthesizer
    synth = PiperSynthesizer.__new__(PiperSynthesizer)
    synth.exe, synth.model = "piper.exe", "voice.onnx"
    args = synth._args(1.25, ["--output_raw"])
    assert isinstance(args, list) and args[0] == "piper.exe" and "--output_raw" in args
