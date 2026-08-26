"""
The self-iterating prompt loop (path-back legs 3b-3e).

Reads market-graded outcomes and works backwards to a better prompt:
  accuracy_monitor  (3c) alerts when a segment's real accuracy drops
  miss_fixtures     (3d) turns a graded miss into a permanent eval case
  prompt_monitor    (3b) compares live prompt versions, may REVERT
  prompt_drafter    (3e) drafts/tests a fix, then pauses for a human
  eval_runner / prompt_gate / prompt_eval_cases -- the offline harness
  prompt_draft_store -- LangGraph checkpoint persistence

NON-NEGOTIABLE (AGENTS.md rules 8/9): nothing in here ever promotes a
prompt to production. Only a human moves that label.
"""
