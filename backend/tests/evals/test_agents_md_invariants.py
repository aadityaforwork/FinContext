"""
AGENTS.md invariant tests
==========================
AGENTS.md was growing every time we hit a bug, because every fix got written
up as prose ("don't do X, we tried it, it broke Y") instead of a check. That
doesn't scale — the doc becomes something nobody actually reads top to
bottom, which defeats the point of a rule.

The split going forward (see AGENTS.md's own note on this):
  - Can a machine check it? -> put the check here (or a hook/schema), and
    trim the prose in AGENTS.md down to a one-line pointer at this file.
  - Is it only true/relevant in one area of the codebase? -> memory/*.md,
    read on demand when touching that area, not loaded into every prompt.
  - Otherwise (always true, not machine-checkable) -> stays in AGENTS.md.

This file is the first bucket: regression tests for rules that used to be
paragraphs of prose and are actually just assertions. No API key, no
network, no Supabase — pure static/text checks, safe to run on every push.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


# ---------------------------------------------------------------------------
# AGENTS.md rule 5: GROUNDING_CONTRACT is intentionally reworded (not
# byte-identical) in ai_client.py vs agents/base.py -- one is a system prompt,
# the other is CrewAI backstory text -- but both must keep the same core
# anti-hallucination doctrine. This doesn't demand literal duplication; it
# demands that editing one copy can't silently drop a rule the other still
# has. See "Known gaps" in AGENTS.md for why this pair exists at all.
# ---------------------------------------------------------------------------
def test_grounding_contract_core_doctrine_present_in_both_copies():
    from app.agents.base import GROUNDING_CONTRACT as agent_contract
    from app.services.ai_client import GROUNDING_CONTRACT as prompt_contract

    # Markers for the four hard rules both copies must restate: cite-only,
    # null+data_gaps for unsupported fields, {text,source} objects (no bare
    # strings), and a top-level confidence field. (A 5th rule diverges by
    # design -- JSON-formatting instruction on the prompt side vs a SEBI/
    # compliance-framing instruction on the agent side -- that's fine, this
    # test only locks the shared doctrine, not full parity.)
    core_markers = [
        "ONLY facts",
        "null",
        "data_gaps",
        "text",
        "source",
        "No bare strings",
        "confidence",
        "low",
        "medium",
        "high",
    ]
    for marker in core_markers:
        assert marker in prompt_contract, f"ai_client.GROUNDING_CONTRACT dropped: {marker!r}"
        assert marker in agent_contract, f"agents.base.GROUNDING_CONTRACT dropped: {marker!r}"


# ---------------------------------------------------------------------------
# "Known gaps" incident: crewai in pyproject.toml -> Vercel bundle > 500MB ->
# every prod deploy fails (frontend included, single deployment). Full story
# in memory/gotcha_crewai_deploy.md. The invariant that must never regress:
# crewai stays in requirements.txt (Render), stays OUT of pyproject.toml
# (Vercel).
# ---------------------------------------------------------------------------
def test_crewai_absent_from_pyproject_toml():
    data = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    offenders = [d for d in deps if d.strip().lower().startswith("crewai")]
    assert not offenders, (
        f"crewai found in pyproject.toml dependencies: {offenders} — this blew the Vercel "
        "500MB function bundle limit on 2026-08-11 (see memory/gotcha_crewai_deploy.md). "
        "crewai must stay in requirements.txt only."
    )


def test_crewai_pinned_in_requirements_txt():
    lines = (BACKEND_ROOT / "requirements.txt").read_text().splitlines()
    non_comment = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    crewai_lines = [ln for ln in non_comment if re.match(r"^crewai(\[|==|>=|$)", ln.strip())]
    assert crewai_lines, "crewai isn't pinned in requirements.txt — Render needs it for real agent surfaces."
    # Deliberately pinned (==), not a floor -- see requirements.txt's own comment on why.
    assert "==" in crewai_lines[0], f"crewai should be exact-pinned (==), got: {crewai_lines[0]!r}"


# ---------------------------------------------------------------------------
# registry.py convention: every CrewAI Agent(...) is built through
# registry._agent() so max_iter/max_execution_time/model selection stay
# consistent. Grep-based, deliberately simple -- catches the case that
# actually happened before (someone reaching for Agent(...) inline in a new
# crew file instead of adding a make_<role>() factory).
# ---------------------------------------------------------------------------
def test_agent_only_instantiated_in_registry():
    agents_dir = BACKEND_ROOT / "app" / "agents"
    offenders = []
    for path in agents_dir.rglob("*.py"):
        if path.name == "registry.py":
            continue
        code_lines = [
            ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("#")
        ]
        # No whitespace before "(" -- a real call, not prose like "every Agent (see ...)".
        if any(re.search(r"(?<![.\w])Agent\(", ln) for ln in code_lines):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"Agent(...) instantiated outside registry.py in: {offenders} — add a make_<role>() "
        "factory to registry.py instead (see its module docstring)."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
