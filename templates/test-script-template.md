# UAT test script: <agent name>

| Field | Value |
|---|---|
| Tester (business user) | |
| Date | |
| Agent build / model / prompt version | |
| Environment and test data set | |

## <Scenario ID>: <title> (<priority>)

**Given**
- <precondition>

**When** <what the user does or says>

**Then** (check each)
- [ ] <observable outcome>

**Agent should call:** `<tool>`  **Agent must NOT call:** `<tool>`

**Guardrails**
- [ ] <safety/privacy/policy check>

Result: ☐ Pass ☐ Fail ☐ Blocked   Runs: __ / __ passed   Defect ID(s): ______

Evidence (transcript link / screenshot): ______

Notes: ______

> Tip: `agent-uat script --scenarios scenarios.json` fills this template from your scenarios.
