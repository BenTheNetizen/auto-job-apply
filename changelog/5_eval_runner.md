# 5. Eval runner

- `evals/run_evals.py`: real extract->plan->fill pipeline against the mock
  ATS sites, agent-as-human review (patch/confirm/submit via review API),
  scoring vs gold labels (required_completion gate + answer_fidelity),
  Langfuse score_eval per case + overall, results JSON in evals/results/,
  exit non-zero when overall required_completion < 1.0.
- `evals/mock-sites/server.mjs`: programmatic vite createServer entry
  (CLI boot path never verified for the submit-recorder middleware).
- Localhost plugin wrappers registered so mock routes dispatch to real
  per-ATS selectors.
- Deps: httpx (review API client), pydantic (explicit), pyproject/uv.lock
  dep union restored after carry-dep merges.
- Carry-dep merges: filler-submitter, mock-sites ESM middleware fix
  (neither was on main; parent merges in order).
