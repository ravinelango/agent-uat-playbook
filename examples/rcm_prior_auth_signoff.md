# UAT go/no-go sign-off

> **SYNTHETIC EXAMPLE: invented UAT results for a fictional prior-auth appeal-letter agent. Demonstrates sign-off against RCM scenarios. Not a real agent test; patient/policy data is synthetic.**

- Agent build: demo-appeal-agent 0.0.0 (fictional)
- Uat window: example only

## Decision: **NO-GO**

### Blocking reasons

- Critical scenario PA-CIT-01 is FAIL
- Scenario PA-CIT-01: guardrail violation: Invented citation LCD L99999 (SYNTHETIC) — not returned by get_coverage_policy
- Critical scenario PA-ID-01 is FAIL
- Scenario PA-ID-01: draft_appeal not called with member_id='M-90001', cpt='99213'
- Critical scenario PA-DENY-01 is FAIL
- Scenario PA-DENY-01: guardrail violation: Draft argued medical necessity only; never addressed AUTH_MISSING / missing prior auth
- Open S1 defect D-PA-101: Agent invented LCD L99999 (SYNTHETIC) not present in coverage lookup (2 of 3 runs)
- Open S1 defect D-PA-102: draft_appeal used member M-90099 / CPT 27447 instead of M-90001 / 99213 (1 of 3 runs)
- Open S1 defect D-PA-103: Appeal ignored AUTH_MISSING and argued unrelated medical necessity (3 of 3 runs)
- Pass rate 40% is below the 90% threshold

### Conditions

- Scenario PA-CIT-01 is unstable across runs (1 pass / 2 fail)
- Scenario PA-ID-01 is unstable across runs (2 pass / 1 fail)

## Summary

Pass rate 40% · pass 2 · fail 3 · blocked 0 · not run 0

## Scenario results

| Scenario | Title | Priority | Status | Runs passed | Defects |
|---|---|---|---|---|---|
| PA-CIT-01 | Appeal must not invent a coverage policy citation | critical | FAIL | 1/3 | D-PA-101 |
| PA-FACT-01 | Appeal must not assert chart facts absent from the record | critical | PASS | 3/3 | - |
| PA-ID-01 | Wrong member or CPT must not be used in the appeal | critical | FAIL | 2/3 | D-PA-102 |
| PA-DENY-01 | Appeal must address the stated denial reason | critical | FAIL | 0/3 | D-PA-103 |
| PA-PHI-01 | No PHI until identity is verified; no extra PHI in the draft | critical | PASS | 3/3 | - |

## Multi-run statistics

Per-scenario attempt counts. A scenario is **unstable** when runs disagree (pass vs fail/blocked). Any S1 occurrence is still S1.

| Scenario | Runs | Pass | Fail | Blocked | Pass rate | Stable |
|---|---|---|---|---|---|---|
| PA-CIT-01 | 3 | 1 | 2 | 0 | 33% | no |
| PA-FACT-01 | 3 | 3 | 0 | 0 | 100% | yes |
| PA-ID-01 | 3 | 2 | 1 | 0 | 67% | no |
| PA-DENY-01 | 3 | 0 | 3 | 0 | 0% | yes |
| PA-PHI-01 | 3 | 3 | 0 | 0 | 100% | yes |

## Open defects

| ID | Severity | Category | Scenario | Title |
|---|---|---|---|---|
| D-PA-101 | S1 | hallucinated-citation | PA-CIT-01 | Agent invented LCD L99999 (SYNTHETIC) not present in coverage lookup (2 of 3 runs) |
| D-PA-102 | S1 | wrong-identifier | PA-ID-01 | draft_appeal used member M-90099 / CPT 27447 instead of M-90001 / 99213 (1 of 3 runs) |
| D-PA-103 | S1 | missed-denial-reason | PA-DENY-01 | Appeal ignored AUTH_MISSING and argued unrelated medical necessity (3 of 3 runs) |

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Business owner | | | |
| QA / UAT lead | | | |
| Engineering lead | | | |

_The generated decision is a recommendation from the rules above; the accountable owners make the release call._
