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


# ---------------------------------------------------------------------------
# Render OOM, 2026-08-15. The service runs on Starter (512 MB hard cap) and
# `import app.main` alone already costs ~200 MB. prompt_drafter.py imported
# langgraph at module scope; main.py imports every router at boot; so ~22 MB
# of LangGraph (53 MB standalone, less in-app because it shares pydantic/httpx
# with the rest) sat resident in the long-lived web process for the sake of an
# admin-token cron endpoint that runs once a day. Combined with a dashboard
# fan-out that needs ~240 MB, the instance pinned at 99.99% of the cap.
#
# Same rule crewai already follows (agents/base.py prewarm()): heavy,
# cron-only, or agent-only dependencies are imported INSIDE the function that
# needs them, never at module scope on a path main.py reaches at boot.
#
# Subprocess, not `"langgraph" in sys.modules`, because test_prompt_drafter.py
# legitimately exercises the graph and would poison sys.modules for an
# in-process check depending on test ordering.
# ---------------------------------------------------------------------------
def test_heavy_optional_deps_not_imported_by_app_main():
    import subprocess
    import sys

    # The marker keeps parsing unambiguous: app.main logs to stderr, but a bare
    # empty stdout line is indistinguishable from "probe produced nothing".
    probe = (
        "import sys; import app.main; "
        "print('LEAKED:' + ','.join(sorted(m for m in ('langgraph', 'crewai', 'litellm') "
        "if m in sys.modules)))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"probe failed to import app.main:\n{proc.stderr[-2000:]}"
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("LEAKED:")]
    assert marker, f"probe produced no result line; stdout was:\n{proc.stdout[-2000:]}"
    leaked = [m for m in marker[-1].removeprefix("LEAKED:").split(",") if m]
    assert not leaked, (
        f"{leaked} imported at app.main boot — each of these is tens of MB resident in the "
        "web process on a 512 MB Render Starter box, for code paths a served request never "
        "touches. Move the import inside the function that needs it."
    )


# ---------------------------------------------------------------------------
# llm_cache silent-write-failure, 2026-08-15. LLMCache's datetime columns are
# plain `DateTime` (no timezone=True). asyncpg REJECTS an aware datetime bound
# to such a column ("invalid input for query argument ... can't subtract
# offset-naive and offset-aware datetimes") and fails the whole INSERT, which
# llm_cache.set() swallows as a warning. The 2026-08-11 fix standardised
# `expires_at` on naive UTC but missed `created_at`'s column default, so the
# persistent cross-worker cache tier wrote nothing at all for four days and
# every cold worker re-ran the full news+LLM fan-out it existed to skip.
#
# SQLite (local/CI default) happily accepts aware datetimes, so no amount of
# local testing reproduces this — hence a direct assertion on the defaults.
# ---------------------------------------------------------------------------
def test_llm_cache_datetime_defaults_are_naive():
    from app.db.models import LLMCache

    for col_name in ("created_at", "expires_at"):
        col = LLMCache.__table__.c[col_name]
        assert col.type.timezone is False, (
            f"LLMCache.{col_name} became timezone-aware at the column level — if that's "
            "deliberate, migrate the existing table and drop the naive-UTC convention in "
            "services/llm_cache.py at the same time."
        )
        if col.default is None:
            continue
        produced = col.default.arg({})
        assert produced.tzinfo is None, (
            f"LLMCache.{col_name}'s default produced an AWARE datetime ({produced!r}). "
            "asyncpg rejects that against a naive DateTime column and silently kills every "
            "llm_cache write — use models._utcnow_naive."
        )


# ---------------------------------------------------------------------------
# Every admin-token daily job must actually be SCHEDULED by something.
#
# miss_fixtures (leg 3d) shipped complete — service, router, migration, tests
# — and then sat at zero rows from the day it shipped until 2026-08-25, not
# because anything was broken but because nothing ever called it. The data it
# needed was in the database the whole time; 51 fixtures converted the first
# time the endpoint was hit by hand. accuracy_monitor, prompt_monitor and
# prompt_drafter were in the same silent state.
#
# A leg that nothing invokes is indistinguishable, from the outside, from a
# leg that runs daily and finds nothing to do — which is exactly why it went
# unnoticed for twelve days. So: adding a run-daily endpoint without adding it
# to a workflow now fails here instead of quietly never running.
#
# Static text check only — this asserts a schedule EXISTS, not that any
# particular run succeeded.
# ---------------------------------------------------------------------------
def test_every_daily_job_endpoint_is_scheduled():
    routers_dir = BACKEND_ROOT / "app" / "routers"
    workflows_dir = REPO_ROOT / ".github" / "workflows"

    assert workflows_dir.is_dir(), f"no .github/workflows directory at {workflows_dir}"
    scheduled_text = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(workflows_dir.glob("*.yml"))
    )

    # Find every admin-gated job endpoint: a router with an @router.post whose
    # path looks like a periodic job, plus the router's own prefix.
    job_path_re = re.compile(r'@router\.post\(\s*[\'"](/(?:run-daily|run-pending|check-approvals|compute-daily))[\'"]')
    prefix_re = re.compile(r'APIRouter\(\s*prefix=[\'"]([^\'"]+)[\'"]')

    endpoints: list[tuple[str, str]] = []
    for py in sorted(routers_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        prefix_m = prefix_re.search(text)
        if not prefix_m:
            continue
        for job_m in job_path_re.finditer(text):
            endpoints.append((py.name, prefix_m.group(1) + job_m.group(1)))

    assert endpoints, (
        "found no daily-job endpoints at all — the detection regex in this test has "
        "probably drifted from how routers/*.py declare them."
    )

    unscheduled = [
        (fname, path) for fname, path in endpoints if path not in scheduled_text
    ]
    assert not unscheduled, (
        "these daily-job endpoints are not referenced by any .github/workflows/*.yml, "
        "so nothing will ever call them (they will look healthy and do nothing — see "
        "the miss_fixtures incident above):\n"
        + "\n".join(f"  - {path}  ({fname})" for fname, path in unscheduled)
        + "\n\nAdd them to .github/workflows/path-back-daily.yml (or another workflow). "
        "If a job is deliberately triggered by an external cron instead, reference its "
        "path in a workflow comment so this check can see it."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
