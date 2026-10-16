# Defect triage walkthrough: RCM prior-auth NO-GO (synthetic)

Worked example of applying [`defect-triage-guide.md`](defect-triage-guide.md) to the
**NO-GO** findings in [`examples/rcm_prior_auth_signoff.md`](../examples/rcm_prior_auth_signoff.md).
All scenarios, member IDs, CPT codes, and LCD numbers below are **synthetic fixtures**.

## Starting point

Regenerate the sample sign-off (optional; the checked-in file already matches):

```bash
agent-uat signoff --scenarios examples/rcm_prior_auth_scenarios.json \
                  --results examples/rcm_prior_auth_results.json \
                  --out examples/rcm_prior_auth_signoff.md
```

Decision: **NO-GO**. Blocking items include three open **S1** defects, three critical
scenario fails, guardrail violations, and a 40% pass rate (below the 90% gate).

## Triage each open S1

| Defect | Scenario | What failed | Severity | Category | Fix-before-release? |
| --- | --- | --- | --- | --- | --- |
| D-PA-101 | PA-CIT-01 | Draft cited LCD `L99999` (SYNTHETIC) that `get_coverage_policy` never returned (2 of 3 runs) | **S1** — compliance / invented coverage language | `hallucinated-citation` (or `guardrail-breach`) | **Yes** — any invented citation blocks release |
| D-PA-102 | PA-ID-01 | `draft_appeal` used member `M-90099` / CPT `27447` instead of `M-90001` / `99213` (1 of 3) | **S1** — wrong patient/service identifiers | `tool-arguments` / `wrong-identifier` | **Yes** — single wrong-ID occurrence is still S1 |
| D-PA-103 | PA-DENY-01 | Letter argued medical necessity only; never addressed `AUTH_MISSING` (3 of 3) | **S1** — core appeal goal missed on every run | `missed-denial-reason` / `wrong-answer` | **Yes** — stable miss on the stated denial reason |

### Non-determinism notes (from the guide)

- **PA-CIT-01** and **PA-ID-01** are **unstable** across runs (pass vs fail disagree). Re-run
  rate is already recorded (2/3 and 1/3 fails). Intermittent ≠ ignore.
- **Any single S1 occurrence stays S1**, even when other runs passed (D-PA-102).
- **PA-DENY-01** failed 3/3 — treat as a stable product defect, not flaky infra.

## Meeting checklist (filled for this example)

1. **Reproduce** — `agent-uat signoff` on the synthetic results; multi-run table shows rates.
2. **Agree severity / category** — table above; all three remain S1.
3. **Decide** — fix before release for all three; no accept-with-mitigation while S1s are open.
4. **Link** — each defect already carries its scenario ID (`PA-CIT-01`, `PA-ID-01`,
   `PA-DENY-01`) so the sign-off matrix stays traceable.

## What would flip this to GO (illustrative only)

This is a teaching checklist against the **synthetic** fixtures, not a real release plan:

- Close or re-verify D-PA-101 / D-PA-102 / D-PA-103 after prompt/tooling fixes.
- Critical scenarios PA-CIT-01, PA-ID-01, PA-DENY-01 pass (and stay stable across re-runs).
- No open S1/S2; pass rate meets the configured threshold; guardrail violations cleared.

Until then the generated recommendation stays **NO-GO**. Accountable owners still make the
release call; the report is a structured recommendation, not an automatic ship gate.
