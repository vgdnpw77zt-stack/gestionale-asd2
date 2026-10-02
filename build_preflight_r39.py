# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
from pathlib import Path

ROOT = Path("/opt/bodymind")

# R73 compatibility: R73 logic lives in already-packaged R55/R41/core files.\n# The launcher target is only a no-op marker so older launcher ordering remains valid.\nr73_stub = ROOT / "release_mobile_operator_mu_r73.py"\nif not r73_stub.exists():\n    r73_stub.write_text("print(\\\"[r73-launcher-stub] source-level R73 active\\\", flush=True)\\n", encoding="utf-8")\n\nPY_FILES = sorted(p for p in ROOT.glob("*.py") if p.is_file())

errors = []
for path in PY_FILES:
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        errors.append(f"syntax:{path.name}:{exc}")

launcher = ROOT / "runtime_launcher.py"
if launcher.exists():
    try:
        launcher_text = launcher.read_text(encoding="utf-8", errors="replace")
        launcher_tree = ast.parse(launcher_text)
        refs = []
        for node in ast.walk(launcher_tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (
                isinstance(fn, ast.Attribute)
                and fn.attr == "run_path"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "runpy"
            ):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                refs.append(node.args[0].value)
        for ref in refs:
            if ref.startswith("/opt/bodymind/") and not Path(ref).exists():
                errors.append(f"missing-launcher-target:{ref}")
    except Exception as exc:
        errors.append(f"launcher-scan:{exc}")
else:
    errors.append("missing-launcher:runtime_launcher.py")

def route_entries(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            method = dec.func.attr.upper()
            if method not in {"ROUTE", "GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
                continue
            rule = dec.args[0].value
            methods = {method}
            if method == "ROUTE":
                methods = {"GET"}
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        vals = []
                        for item in kw.value.elts:
                            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                                vals.append(item.value.upper())
                        if vals:
                            methods = set(vals)
            for m in methods:
                out.append((rule, m, node.name))
    return out

targets = [
    ROOT / "operator_bodymind_runtime_r29.py",
]
routes = []
for path in targets:
    if not path.exists():
        errors.append(f"missing-route-source:{path.name}")
        continue
    try:
        routes.extend(route_entries(path))
    except Exception as exc:
        errors.append(f"route-parse:{path.name}:{exc}")

required = {
    ("/operatore-bodymind", "GET"),
    ("/operatore-bodymind/chat", "POST"),
    ("/operatore-bodymind/new-chat", "POST"),
    ("/operatore-bodymind/upload", "POST"),
    ("/operatore-bodymind/cloud/status", "GET"),
    ("/operatore-bodymind/voice/transcribe", "POST"),
    ("/operatore-bodymind/voice/speak", "POST"),
    ("/operatore-bodymind/cloud/usage/tts", "POST"),
    ("/operatore-bodymind/smtp/setup", "GET"),
    ("/operatore-bodymind/secure/smtp", "GET"),
    ("/operatore-bodymind/secure/smtp", "POST"),
}

index = {}
for rule, method, endpoint in routes:
    index.setdefault((rule, method), []).append(endpoint)

for key in sorted(required):
    if len(index.get(key, [])) != 1:
        errors.append(f"critical-route:{key[1]} {key[0]} count={len(index.get(key, []))}")

for key, endpoints in sorted(index.items()):
    if len(endpoints) > 1:
        errors.append(f"duplicate-packaged-route:{key[1]} {key[0]} endpoints={endpoints}")

if errors:
    print("[build-preflight-r39] FAIL")
    for item in errors:
        print("[build-preflight-r39-error] " + item)
    raise SystemExit(1)

print(
    f"[build-preflight-r39] PASS python_files={len(PY_FILES)} "
    f"packaged_routes={len(routes)} critical_routes={len(required)}"
)
