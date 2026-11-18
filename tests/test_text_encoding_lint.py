"""Fail when Python text I/O relies on the machine default encoding.

On Windows the default is cp1252, so a bare text mode open() or read_text()
can crash or garble non English text. Binary mode is exempt.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "build", "dist"}
SUBPROCESS_NAMES = {"run", "check_output", "Popen", "check_call", "call"}
# name -> (position of mode, position of encoding) in the call signature.
# Path.open and NamedTemporaryFile differ from the builtin open() signature.
OPEN_LIKE = {
    "open": {"builtin": (1, 3), "method": (0, 2)},
    "fdopen": {"builtin": (1, 3), "method": (1, 3)},
    "NamedTemporaryFile": {"builtin": (0, 2), "method": (0, 2)},
    "TemporaryFile": {"builtin": (0, 2), "method": (0, 2)},
    "SpooledTemporaryFile": {"builtin": (1, 4), "method": (1, 4)},
}


def python_files():
    for path in sorted(ROOT.rglob("*.py")):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            yield path


def has_star(call):
    return any(isinstance(a, ast.Starred) for a in call.args) or any(
        k.arg is None for k in call.keywords
    )


def arg_at(call, position, keyword):
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    if len(call.args) > position:
        return call.args[position]
    return None


def mode_of(call, position):
    node = arg_at(call, position, "mode")
    if node is None:
        return "r"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None  # not a literal: cannot tell, so treat as text


def call_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr, func.value
    return getattr(func, "id", ""), None


def is_truthy_or_unknown(node):
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return bool(node.value)
    return True


def bare_text_calls(path):
    source = path.read_text(encoding="utf-8")
    problems = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name, owner = call_name(node.func)
        owner_name = owner.id if isinstance(owner, ast.Name) else ""
        keywords = {k.arg for k in node.keywords}
        if has_star(node):
            continue
        if name in ("read_text", "write_text"):
            # Path.read_text(encoding, errors), Path.write_text(data, encoding, ...)
            position = 0 if name == "read_text" else 1
            bad = arg_at(node, position, "encoding") is None
        elif name in OPEN_LIKE:
            if owner_name == "os" and name == "open":
                continue  # os.open is a file descriptor call, not text mode
            if name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile") and (
                owner is not None and owner_name != "tempfile"
            ):
                continue
            if name == "fdopen" and owner_name != "os":
                continue
            if name == "open" and owner is not None and owner_name == "webbrowser":
                continue
            kind = "builtin" if (owner is None or owner_name in ("io", "os", "tempfile", "codecs")) else "method"
            mode_pos, enc_pos = OPEN_LIKE[name][kind]
            if name == "open" and owner_name == "codecs":
                continue  # codecs.open always takes an explicit encoding argument
            if name == "NamedTemporaryFile" or name.endswith("TemporaryFile"):
                default = "w+b"
                mode_node = arg_at(node, mode_pos, "mode")
                if mode_node is None:
                    mode = default
                elif isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
                    mode = mode_node.value
                else:
                    mode = None
            else:
                mode = mode_of(node, mode_pos)
            binary = mode is not None and "b" in mode
            bad = (not binary) and arg_at(node, enc_pos, "encoding") is None
        elif name in SUBPROCESS_NAMES and (owner_name == "subprocess" or owner is None):
            textual = any(
                is_truthy_or_unknown(arg_at(node, 10**6, k))
                for k in ("text", "universal_newlines")
            )
            bad = textual and "encoding" not in keywords
        else:
            continue
        if bad:
            problems.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}() without encoding")
    return problems


class TextEncodingLintTests(unittest.TestCase):
    def test_no_text_io_without_explicit_encoding(self):
        problems = []
        for path in python_files():
            problems.extend(bare_text_calls(path))
        self.assertEqual(problems, [], "Add encoding=\"utf-8\" to:\n" + "\n".join(problems))

    def test_lint_catches_known_bad_shapes(self):
        samples = {
            "open('f')": 1,
            "open('f', 'r')": 1,
            "open('f', 'rb')": 0,
            "open('f', 'w', encoding='utf-8')": 0,
            "open('f', 'w', -1, 'utf-8')": 0,
            "io.open('f', 'w')": 1,
            "io.open('f', 'wb')": 0,
            "os.fdopen(fd, 'w')": 1,
            "os.fdopen(fd, 'wb')": 0,
            "os.fdopen(fd, 'w', encoding='utf-8')": 0,
            "os.open('f', os.O_RDONLY)": 0,
            "p.open()": 1,
            "p.open('rb')": 0,
            "p.open('r', encoding='utf-8')": 0,
            "p.read_text()": 1,
            "p.read_text('utf-8')": 0,
            "p.read_text(encoding='utf-8')": 0,
            "p.write_text('x')": 1,
            "p.write_text('x', 'utf-8')": 0,
            "p.write_text('x', encoding='utf-8')": 0,
            "tempfile.NamedTemporaryFile('w')": 1,
            "tempfile.NamedTemporaryFile()": 0,
            "tempfile.NamedTemporaryFile(mode='w', encoding='utf-8')": 0,
            "tempfile.NamedTemporaryFile('w+', -1, 'utf-8')": 0,
            "subprocess.run(['x'], text=True)": 1,
            "subprocess.run(['x'], text=True, encoding='utf-8')": 0,
            "subprocess.run(['x'], universal_newlines=True)": 1,
            "subprocess.run(['x'], capture_output=True)": 0,
        }
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            for index, (code, expected) in enumerate(samples.items()):
                sample = Path(tmp) / f"sample_{index}.py"
                sample.write_text(code + "\n", encoding="utf-8")
                found = bare_text_calls_for_sample(sample)
                self.assertEqual(len(found), expected, code)


def bare_text_calls_for_sample(path):
    global ROOT  # bare_text_calls reports paths relative to ROOT
    original = ROOT
    ROOT = path.parent
    try:
        return bare_text_calls(path)
    finally:
        ROOT = original


if __name__ == "__main__":
    unittest.main()
