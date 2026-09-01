#!/usr/bin/env python
"""PostToolUse hook: run `ruff check` on backend/*.py files after Edit/Write.

Reads the hook JSON payload from stdin. If the edited/written file is a
Python file under backend/, runs ruff check against just that file, using
the project's own backend venv ruff so results match what CI's
`ruff check .` (see .github/workflows/ci.yml) would report.

Emits nothing when clean. On findings, returns
hookSpecificOutput.additionalContext so the model sees the lint output
immediately instead of waiting for CI to go red a few minutes later.

Never blocks the edit -- decision is left unset (default: continue) even
when ruff reports issues. This is a fast local nudge, not an enforcement
gate; flip that later if you want it to actually block.
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ruff_exe() -> str:
    for candidate in (
        os.path.join(REPO_ROOT, "backend", "venv", "Scripts", "ruff.exe"),
        os.path.join(REPO_ROOT, "backend", "venv", "bin", "ruff"),
        os.path.join(REPO_ROOT, "backend", ".venv", "Scripts", "ruff.exe"),
        os.path.join(REPO_ROOT, "backend", ".venv", "bin", "ruff"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return "ruff"  # fall back to whatever's on PATH


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or (payload.get("tool_response") or {}).get("filePath") or ""
    if not file_path:
        return 0

    if not os.path.isabs(file_path):
        file_path = os.path.join(REPO_ROOT, file_path)
    file_path = os.path.abspath(file_path)
    norm = file_path.replace("\\", "/")
    if not norm.endswith(".py"):
        return 0
    if "/backend/" not in norm and not norm.startswith("backend/"):
        return 0
    if not os.path.isfile(file_path):
        return 0

    result = subprocess.run(
        [_ruff_exe(), "check", file_path],
        cwd=os.path.join(REPO_ROOT, "backend"),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 0

    findings = (result.stdout or result.stderr).strip()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"ruff check found issues in {file_path}:\n{findings}",
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
