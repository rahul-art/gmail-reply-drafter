# AI Gmail Reply & Invoice Drafter (Human-in-the-Loop)

A config-driven AI agent that reads an inbox, selects or drafts tailored replies/invoices using **structured templates**, and saves them directly as **Gmail drafts** with thread continuity. 

> **Important**: This agent **never sends emails automatically**. Every draft is saved in Gmail under the `AI-Drafted` label for human review, verification, and manual approval before sending.

## Workflow

```
inbox ──► guardrail check ──► AI picks template + fills blanks ──► render template ──► Gmail draft + label
              │ (phishing / bank change)       │ (unsure / blanks missing)
              └──────────► ESCALATE ◄──────────┘   (labeled, no draft)
```

- **Invoices & Proposals on Autopilot**: When a client requests milestone billing or an invoice, the AI drafts the milestone details, terms, and amounts, leaving it ready for quick verification and 1-click sending.
- **Config-Driven Architecture**: Personal branding, service domains, templates, and guardrail rules live in `config.yaml`.
- **Zero Hallucination / Half-Filled Drafts**: Uses enforced JSON schema structured output. If critical details are absent, it safely falls back to a scoping request (`need_more_info`) or escalates.
- **Strict Security Guardrails**: Phishing attempts, fraudulent bank/wire account changes, chargebacks, and legal threats are intercepted by deterministic rules before hitting the AI model.
- **Multi-Model Resilience**: Primary support for Google Gemini (`gemini-3.1-flash-lite`, `gemini-flash-latest`) with automatic retry and seamless fallback to Anthropic Claude.

---

## Getting Started

### 1. Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Keys
Add your API keys to `.env` (automatically loaded, ignored by Git):
```bash
GEMINI_API_KEY=your_gemini_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 3. Run Offline or Against Test Cases
```bash
# Offline demo with mock rule-based stand-in
python drafter.py --sample --mock --test-week

# With real AI (Gemini or Claude fallback)
python drafter.py --sample --test-week
```

### 4. Connect to Live Gmail
1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Gmail API**.
2. Create an **OAuth 2.0 Desktop Client ID** and download it as `credentials.json` into this directory.
3. Run the drafter:
   ```bash
   python drafter.py --gmail
   ```
4. Complete the one-time browser consent screen. The agent will fetch unread inquiries, generate drafts in your Gmail threads, and apply the `AI-Drafted` label.

---

## File Structure

| File | Description |
|---|---|
| `drafter.py` | Pipeline: guardrail screening, structured AI decision, template rendering, and Gmail draft creation |
| `config.yaml` | Service definitions, reply templates, signature, and security guardrails |
| `templates/*.md` | Templates for project proposals, invoice drafts, scoping clarification, and out-of-scope replies |
| `sample_emails.json` | Sample test cases covering project inquiries, invoice requests, and security escalations |
| `LOOM_SCRIPT.md` | 75-second video walkthrough script |
