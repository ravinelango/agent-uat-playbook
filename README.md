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
| [`examples/`](examples/) | **Synthetic** support-agent scenarios and results, with generated outputs |

## Quickstart
```bash
pip install -e '.[dev]'
agent-uat validate --scenarios examples/support_agent_scenarios.json
agent-uat script   --scenarios examples/support_agent_scenarios.json --out reports/script.md
agent-uat signoff  --scenarios examples/support_agent_scenarios.json \
                   --results examples/support_agent_results.json --out reports/signoff.md
```
Add `--strict` to make `signoff` exit 1 unless the decision is GO (useful as a release gate).
See [`examples/sample_signoff.md`](examples/sample_signoff.md): the synthetic run is a
**NO-GO** because the agent acted on a prompt injection in 1 of 3 runs.

### Filling `actual_tool_calls` from traces

If the agent is instrumented with OpenTelemetry (GenAI semantic conventions, `execute_tool`
spans), let the trace say which tools ran instead of copying them by hand:

```bash
agent-uat trace --trace examples/traces/support_agent_otlp.json \
  --scenario-id REF-01 --session run-1
```

This prints a results entry (`scenario_id` + `actual_tool_calls` in start-time order) to
paste or merge into your results file. Add `--with-args` to include each call's arguments
(`tool_call_details`), which the argument checks below use.
The bundled trace is a hand-written synthetic example.

### Tool-call order and argument checks

A scenario can require that the expected tools run in sequence and that a tool gets the
right arguments, so "called `create_refund_request`" isn't counted as a pass when it was
called before the order lookup, or on the wrong order:

```json
"expected_tool_calls": ["lookup_order", "create_refund_request"],
"ordered_tool_calls": true,
"tool_argument_checks": [{"tool": "create_refund_request", "args": {"order_id": "A1001"}}]
```

## Decision rules (v0.1)
**NO-GO** if a critical scenario failed, was blocked or wasn't run; the agent called a
forbidden tool; a guardrail violation was recorded; an S1/S2 defect is open; or the pass rate
is below the threshold (default 90%, `--min-pass-rate`); or a critical scenario called its
expected tools out of order or with the wrong arguments.
**GO WITH CONDITIONS** if there are open S3 defects, non-critical scenarios not run, or
expected tool calls that were missed, order or argument mismatches on non-critical scenarios,
or argument checks that couldn't be verified because the result had no `tool_call_details`.
**GO** otherwise.

## Status
**Early, v0.1.** The format, templates, guide and CLI work and are tested. The example
agent, scenarios and results are **synthetic** and exist only to demonstrate the format.
**No real agent UAT results are published here.**

## Roadmap
- ~~Fill `actual_tool_calls` from OpenTelemetry traces~~ (done: `agent-uat trace`); Langfuse export next
- ~~Tool-call order and argument checks~~ (done: `ordered_tool_calls`, `tool_argument_checks`)
- Multi-run statistics per scenario
- HTML sign-off report and a traceability link to defect trackers

## License
MIT © Ravin Elango
