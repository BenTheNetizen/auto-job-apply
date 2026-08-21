# Mock ATS Sites

Vite + React app mimicking Ashby, Greenhouse, and Lever application forms for
evaluating the application-filling pipeline without touching the internet.

## Run

```bash
npm install --prefix evals/mock-sites
npm run dev --prefix evals/mock-sites   # serves http://localhost:5173
```

## Routes

| Route | Notes |
|---|---|
| `/ashby/basic` | core flavors: text, file, textarea, radio |
| `/ashby/screening` | date, select, radio, salary |
| `/ashby/demographics` | checkbox-group, veteran/disability/gender selects |
| `/greenhouse/basic` | `#application` root, expand-all demographics |
| `/greenhouse/select2` | selects hidden behind select2-style widgets |
| `/greenhouse/demographics` | full demographic matrix |
| `/lever/basic` | `div.application-form` root |
| `/lever/accordion` | sections behind `.toggle` accordion headers |
| `/lever/demographics` | full demographic matrix |

`/` lists all cases.

## Submit recording

Forms POST `{applicationId, fields}` to `/submit`; a Vite dev-server plugin
writes the payload to `submissions/<ats>__<case>.json` for the eval runner to
score against `gold/<ats>__<case>.json`.

## Gold labels

`gold/<case>.json` — pydantic-parsed by `evals/mock_sites_gold.py`. Each field
has `key, label, type, required, expected`. `expected: "@generated@"` means the
answer is LLM-generated (short answers); the scorer checks content rules
instead of exact match. All other expected values derive from the mock profile
`evals/fixtures/mock_profile.csv` (Taylor Wong <taylor.wong@agentmail.to>).
