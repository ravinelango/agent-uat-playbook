# RCM prior-auth appeal UAT example (synthetic)

This repo ships a second **synthetic** example beside the support-agent set: scenarios and
results for signing off an LLM **prior-authorization appeal-letter** agent in a revenue-cycle
(RCM) context.

| File | Role |
| --- | --- |
| [`examples/rcm_prior_auth_scenarios.json`](../examples/rcm_prior_auth_scenarios.json) | Given/When/Then + tools/guardrails for citation, chart-fact, identifier, denial-reason, and PHI checks |
| [`examples/rcm_prior_auth_results.json`](../examples/rcm_prior_auth_results.json) | Invented multi-run results that produce a **NO-GO** (open S1 defects + critical fails) |
| [`examples/rcm_prior_auth_signoff.md`](../examples/rcm_prior_auth_signoff.md) | Generated sample sign-off (regenerate with the CLI below) |

## Failure modes covered

These mirror the checkers in the separate **prior-auth-appeal-eval** project (not required to
run this example):

1. **Invented coverage citation** — draft cites an LCD/NCD/policy ID that tools never returned.
2. **Chart fact not in record** — draft asserts imaging, failed therapy, or labs absent from notes.
3. **Wrong member / CPT** — identifiers from another synthetic member leak into `draft_appeal`.
4. **Missed denial reason** — letter never addresses the stated reason (e.g. `AUTH_MISSING`).
5. **PHI / identity** — chart access or draft before `verify_identity`, or extra PHI in the letter.

All member IDs, claim IDs, CPT/ICD codes, payer policy numbers, SSNs, and addresses in the
JSON are **synthetic fixtures**. Do not treat them as real PHI or real coverage rules.

## Reproduce the sample sign-off

```bash
agent-uat validate --scenarios examples/rcm_prior_auth_scenarios.json
agent-uat signoff  --scenarios examples/rcm_prior_auth_scenarios.json \
                   --results examples/rcm_prior_auth_results.json \
                   --out examples/rcm_prior_auth_signoff.md
```

Expect **NO-GO**: critical scenarios failed, guardrail violations on invented citation and
missed denial reason, wrong `draft_appeal` arguments on PA-ID-01, and open S1 defects.

## Defect triage walkthrough

For a step-by-step severity/category pass over the three open S1 defects (D-PA-101,
D-PA-102, D-PA-103), see
[`docs/rcm-defect-triage-walkthrough.md`](rcm-defect-triage-walkthrough.md).
