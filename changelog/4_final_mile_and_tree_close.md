# Final mile + spec tree close

- Final-mile adversarial review (3 reviewers): 3 blockers fixed — post-click double-submit guard, canonical `|` multi-value separator (prompt/fixture/filler aligned), plugin `form_root` selector key standardization.
- Nice-to-have batch: learning LLM degradation, plugin export naming, greenhouse hostname_matches, click dep, template placeholder cleanup, email-monitor top-level-status guard, per-field fill guards, status-parser dead branch collapse.
- E2E verification: eval gate run_evals.py exits 0 with required_completion=1.0 across all 9 mock Ashby/Greenhouse/Lever cases; 292 tests green.
- Spec tree closed: 20/20 core leaves COMPLETED, 4/5 subsystems COMPLETED. live-fire-smoke remains Defined (stretch — needs a real posting URL from the user).
- Deferred/future: live-fire-smoke; React dashboard; job-discovery subsystem; Supabase migration; webhook-based email; CSV→fidelity gating once separator semantics settle.
