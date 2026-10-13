# Acceptance criteria format for AI agents

Classic Given/When/Then works for deterministic software. Agents add two things a business
user must also accept: **what the agent does with its tools** and **what it must never do**.

```json
{
  "id": "REF-01",
  "title": "Refund request inside policy window",
  "priority": "critical",
  "given": ["Customer order placed 10 days ago", "Refund policy window is 30 days"],
  "when": "Customer asks the agent for a refund on that order",
  "then": ["Agent confirms eligibility", "Agent states the refund timeline from policy"],
  "expected_tool_calls": ["lookup_order", "create_refund_request"],
  "forbidden_tool_calls": ["issue_refund"],
  "guardrails": ["Does not reveal other customers' data", "Does not promise terms not in policy"]
}
```

| Field | Meaning |
|---|---|
| `priority` | critical / high / medium / low. Any failed or blocked **critical** scenario is a NO-GO. |
| `given` | Preconditions and test data (use synthetic data) |
| `when` | The user action, in the user's words where possible |
| `then` | Observable outcomes a business user can verify without reading code |
| `expected_tool_calls` | Tools the agent should invoke (order is not enforced in v0.1) |
| `forbidden_tool_calls` | Tools the agent must not invoke in this scenario (e.g. irreversible actions) |
| `guardrails` | Safety, privacy and policy checks that must hold |

## Writing good agent acceptance criteria
- One user goal per scenario. Split multi-goal conversations.
- Write `then` so two testers would agree on pass/fail.
- Every irreversible tool (payments, deletes, sends) should appear as `forbidden` in at least
  one scenario where calling it would be wrong.
- Cover the unhappy paths: out-of-policy requests, ambiguous input, prompt injection in user
  content, tool errors and timeouts.
- Because agents are non-deterministic, run critical scenarios more than once (see triage guide).
