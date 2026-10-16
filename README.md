# agent-uat-playbook

[![CI](https://github.com/ravinelango/agent-uat-playbook/actions/workflows/ci.yml/badge.svg)](https://github.com/ravinelango/agent-uat-playbook/actions/workflows/ci.yml)
![status](https://img.shields.io/badge/status-early%20(v0.1)-orange)
![license](https://img.shields.io/badge/license-MIT-blue)

**User acceptance testing (UAT) for AI agents:** acceptance criteria a business user can sign,
a test script they can follow, a triage guide for what they find, and a go/no-go report
generated from the results.

## Why UAT for agents is different
Offline evals tell engineers how a model scores. UAT answers the business question: *will
this agent do the job for our users without doing anything it must never do?* Agents add
problems classic UAT templates don't cover:

- **Actions, not just answers.** Acceptance must include which tools the agent calls, and
  which irreversible tools (refunds, deletes, sends) it must *not* call.
- **Guardrails are acceptance criteria.** Privacy, policy and prompt-injection behavior get
  explicit checks, not an afterthought.
- **Non-determinism.** The same scenario can pass twice and fail once. The triage guide
  records reproduction rates and treats any S1 occurrence as S1.
- **A clear decision.** Results roll up into GO / GO WITH CONDITIONS / NO-GO with the reasons
  listed, and the accountable owners still sign.

## What's inside
| Path | What it is |
|---|---|
| [`docs/acceptance-criteria-format.md`](docs/acceptance-criteria-format.md) | Given/When/Then + expected tool calls, forbidden tool calls, guardrails |
| [`templates/test-script-template.md`](templates/test-script-template.md) | Business-user test script template |
| [`docs/defect-triage-guide.md`](docs/defect-triage-guide.md) | Severity (S1-S4), agent defect categories, non-determinism rules |
| `agent-uat` CLI | Validates scenarios, renders test scripts, generates the sign-off report |
| [`examples/`](examples/) | **Synthetic** support-agent and RCM prior-auth scenarios/results, with generated outputs |
| [`docs/rcm-prior-auth-example.md`](docs/rcm-prior-auth-example.md) | RCM prior-auth appeal UAT example (all patient/policy data synthetic) |
| [`docs/rcm-defect-triage-walkthrough.md`](docs/rcm-defect-triage-walkthrough.md) | Walkthrough of triage for the RCM NO-GO S1 defects (synthetic) |

## Quickstart
```bash
pip install -e '.[dev]'
agent-uat validate --scenarios examples/support_agent_scenarios.json
agent-uat script   --scenarios examples/support_agent_scenarios.json --out reports/script.md
agent-uat signoff  --scenarios examples/support_agent_scenarios.json \
                   --results examples/support_agent_results.json --out reports/signoff.md
```
Add `--strict` to make `signoff` exit 1 unless the decision is GO (useful as a release gate).
See [`examples/sample_signoff.md`](examples/sample_signoff.md) (and the print-friendly
[`examples/sample_signoff.html`](examples/sample_signoff.html)): the synthetic run is a
**NO-GO** because the agent acted on a prompt injection in 1 of 3 runs. Pass `--format html`
or an `--out` path ending in `.html` for the HTML report.

### RCM prior-auth appeal example (synthetic)

A second fixture set signs off an LLM **prior-authorization appeal-letter** agent
(citation, chart-fact, wrong member/CPT, missed denial reason, PHI/identity):

```bash
agent-uat validate --scenarios examples/rcm_prior_auth_scenarios.json
agent-uat signoff  --scenarios examples/rcm_prior_auth_scenarios.json \
                   --results examples/rcm_prior_auth_results.json \
                   --out examples/rcm_prior_auth_signoff.md
```

See [`docs/rcm-prior-auth-example.md`](docs/rcm-prior-auth-example.md) and
[`examples/rcm_prior_auth_signoff.md`](examples/rcm_prior_auth_signoff.md): the synthetic
run is a **NO-GO** (invented LCD citation, wrong identifiers, missed `AUTH_MISSING`).
Member IDs, claims, CPT codes, and policy numbers are fixtures — not real PHI.

### Filling `actual_tool_calls` from traces

If the agent is instrumented with OpenTelemetry (GenAI semantic conventions, `execute_tool`
spans) or you have a **Langfuse-like** JSON export (`observations` with tool markers), let
the trace say which tools ran instead of copying them by hand:

```bash
agent-uat trace --trace examples/traces/support_agent_otlp.json \
  --scenario-id REF-01 --session run-1

# Langfuse-like synthetic export (auto-detected, or pass --format langfuse)
agent-uat trace --trace examples/traces/support_agent_langfuse.json \
  --scenario-id REF-01 --session run-1 --format langfuse
```

This prints a results entry (`scenario_id` + `actual_tool_calls` in start-time order) to
paste or merge into your results file. Add `--with-args` to include each call's arguments
(`tool_call_details`), which the argument checks below use.
The bundled traces are hand-written **synthetic** examples (OTLP and Langfuse-like), not
real production dumps.

### Tool-call order and argument checks

A scenario can require that the expected tools run in sequence and that a tool gets the
right arguments, so "called `create_refund_request`" isn't counted as a pass when it was
called before the order lookup, or on the wrong order:

```json
"expected_tool_calls": ["lookup_order", "create_refund_request"],
"ordered_tool_calls": true,
"tool_argument_checks": [{"tool": "create_refund_request", "args": {"order_id": "A1001"}}]
```

### Multi-run statistics

Agents are non-deterministic: the same scenario can pass twice and fail once. Each result
row can record attempts as `runs_passed` / `runs_total` (and optional `runs_blocked`), or
as an explicit `run_outcomes` list (`pass` / `fail` / `blocked` per attempt). The sign-off
report adds a **Multi-run statistics** table (runs, pass/fail/blocked counts, pass rate,
stable yes/no). Mixed outcomes mark the scenario **unstable** and become a condition; any
S1 occurrence is still S1 (see the triage guide).

## Decision rules (v0.1)
**NO-GO** if a critical scenario failed, was blocked or wasn't run; the agent called a
forbidden tool; a guardrail violation was recorded; an S1/S2 defect is open; or the pass rate
is below the threshold (default 90%, `--min-pass-rate`); or a critical scenario called its
expected tools out of order or with the wrong arguments.
**GO WITH CONDITIONS** if there are open S3 defects, non-critical scenarios not run, or
expected tool calls that were missed, order or argument mismatches on non-critical scenarios,
argument checks that couldn't be verified because the result had no `tool_call_details`, or a
scenario is unstable across runs (mixed pass/fail/blocked).
**GO** otherwise.

## Status
**Early, v0.1.** The format, templates, guide and CLI work and are tested. The example
agent, scenarios and results are **synthetic** and exist only to demonstrate the format.
**No real agent UAT results are published here.**

## Roadmap
- ~~Fill `actual_tool_calls` from OpenTelemetry / Langfuse-like traces~~ (done: `agent-uat trace`, `--format auto|otlp|langfuse`)
- ~~Tool-call order and argument checks~~ (done: `ordered_tool_calls`, `tool_argument_checks`)
- ~~Multi-run statistics per scenario~~ (done: pass/fail/blocked counts, pass rate, unstable flag)
- ~~HTML sign-off report~~ (done: `agent-uat signoff --format html` or `--out ….html`)
- Traceability link to defect trackers

## License
MIT © Ravin Elango
