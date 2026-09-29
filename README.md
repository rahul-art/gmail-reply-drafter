# Gmail Reply Drafter

A small, config-driven Claude agent that reads a business inbox, picks one of the **client's own reply templates**, fills in its blanks, and saves the result as a **Gmail draft**. It never sends anything. A person reviews every draft and sends it themselves.

## How it works

```
inbox ──► guardrail check ──► Claude picks template + fills blanks ──► render client's template ──► Gmail draft + label
              │ (money/legal words)          │ (unsure / blanks missing)
              └──────────► ESCALATE ◄─────────┘   (labelled, no draft)
```

- **The config sets it up, not the code.** Client name, templates, service area, the Gmail search and the guardrails all live in `config.yaml`. A new client means a new config, with no code changes.
- **The client's voice stays theirs.** Claude doesn't write the email. It picks a template and fills the blanks through a forced tool call (structured output). The template text goes out exactly as the client wrote it.
- **Money and legal emails never reach the model.** Anything mentioning invoices, refunds, payments, banks, complaints or contracts is escalated by a deterministic keyword check before any AI call.
- **No half-filled drafts.** If Claude leaves a blank empty, the email is escalated instead.
- **Test-week mode.** Run it against known cases. It reports matched/total and writes `mismatches.csv` (case, expected, actual, reason) for review.

## Run it

```bash
pip install -r requirements.txt

# 1. Offline demo, no keys needed (rule-based stand-in for Claude)
python drafter.py --sample --mock --test-week

# 2. With Gemini (or Claude fallback)
# Set GEMINI_API_KEY in .env or export GEMINI_API_KEY=... / ANTHROPIC_API_KEY=...
python drafter.py --sample --test-week

# 3. Real Gmail inbox -> drafts
#    Google Cloud Console: enable the Gmail API, create an OAuth "Desktop app" client,
#    and save it as credentials.json in this folder. The first run opens a browser to consent.
python drafter.py --gmail
```

To use it with your own Gmail, change `service_area` and the templates in `config.yaml` to match your test emails, or send yourself a few test emails.

## Files

| File | What it is |
|---|---|
| `drafter.py` | The pipeline: guardrails, Claude tool call, rendering, Gmail drafts, test-week log |
| `config.yaml` | Client setup filled from a (sample) mapping session |
| `templates/*.md` | The client's own reply templates |
| `sample_emails.json` | Four test cases, including one that must escalate |

## Security notes

- OAuth scope is `gmail.modify` (read, label, draft). The code has no send call anywhere.
- `credentials.json` and `token.json` stay on the machine running the tool. Add them to `.gitignore`.
- Email content goes only to the Claude API for the decision. Nothing is written to disk except the mismatch log, which holds subjects and decisions only.
