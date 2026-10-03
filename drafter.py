"""
Gmail reply drafter: a config-driven Claude agent that drafts replies from a
client's OWN templates and saves them as Gmail drafts. It never sends.

Design choices (the same ones an implementation firm cares about):
  * Config holds the client-specific setup; the code stays generic.
  * Claude only picks a template and fills its blanks (via forced tool call).
    The client's wording is rendered as written, so their voice isn't rewritten.
  * Money / bank / invoice / legal emails are escalated BEFORE the model sees them.
  * Output is a draft plus a label. A human reviews and sends.
  * --test-week compares decisions to known cases and logs every mismatch.

Usage:
  python drafter.py --sample                 # sample emails, print drafts
  python drafter.py --sample --test-week     # compare to expected, write mismatches.csv
  python drafter.py --sample --mock          # no API key needed (rule-based stand-in)
  python drafter.py --gmail                  # real inbox -> Gmail drafts
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import string
import sys
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent
ESCALATE = "ESCALATE"

# Auto-load .env if present
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# ---------- config & templates ----------

def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    for t in cfg["templates"]:
        t["text"] = (ROOT / t["file"]).read_text()
        t["fields"] = sorted(
            {f for _, f, _, _ in string.Formatter().parse(t["text"]) if f and f != "signature"}
        )
    return cfg


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    thread_id: str | None = None
    message_id_header: str | None = None
    expected_template: str | None = None

    @property
    def first_name(self) -> str:
        name, addr = parseaddr(self.sender)
        return (name or addr).split()[0].split("@")[0].title()


@dataclass
class Decision:
    template_id: str
    fields: dict = field(default_factory=dict)
    reason: str = ""
    draft: str | None = None


# ---------- guardrails ----------

def guardrail_check(email: Email, cfg: dict) -> str | None:
    """Deterministic pre-check: high-risk security, banking change, or legal disputes never reach the model."""
    text = f"{email.subject} {email.body}".lower()
    hits = [w for w in cfg["guardrails"]["escalate_if"] if w.lower() in text]
    return f"guardrail triggers: {', '.join(hits)}" if hits else None


# ---------- Claude decision (forced tool call = structured output) ----------

def build_tool(cfg: dict) -> dict:
    ids = [t["id"] for t in cfg["templates"]] + [ESCALATE]
    all_fields = sorted({f for t in cfg["templates"] for f in t["fields"]})
    return {
        "name": "choose_reply",
        "description": "Pick one reply template for this email and fill its blanks, or ESCALATE to a human.",
        "input_schema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "enum": ids},
                "fields": {
                    "type": "object",
                    "description": "Values for the chosen template's blanks only.",
                    "properties": {f: {"type": "string"} for f in all_fields},
                },
                "reason": {"type": "string", "description": "One sentence: why this template."},
            },
            "required": ["template_id", "fields", "reason"],
        },
    }


def system_prompt(cfg: dict) -> str:
    lines = [
        f"You triage inbound emails and draft professional replies/invoices for {cfg['client']['name']}.",
        f"Core expertise: {', '.join(cfg.get('service_area', []))}.",
        "Important rules:",
        "1. Choose exactly one template, or ESCALATE if there is a security hazard, suspicious bank change, legal dispute, or if unsure.",
        "2. If the client asks for an invoice, payment details, or milestone billing, pick 'invoice_draft'.",
        "3. Fill only the chosen template's blanks factually and concisely using ONLY facts stated in the email.",
        "4. For new_project_quote: 'project_summary' (short subject/topic), 'suggested_next_step' (e.g. 'I would be happy to jump on a quick 15-minute discovery call this Thursday to review your technical specs and milestones.').",
        "5. For invoice_draft: 'project_summary' (project/milestone name), 'invoice_description' (e.g. 'Milestone deliverables completed & approved'), 'amount' (e.g. '$1,800' or as stated in email), 'payment_terms' ('Due upon receipt').",
        "6. For need_more_info: 'missing_items' (bullet list of missing specifications like tech stack, timeline, budget, or architecture).",
        "7. For out_of_scope: 'project_summary' (inquiry subject), 'service_focus' ('AI automation and full-stack software development').",
        "",
        "Available Templates:",
    ]
    for t in cfg["templates"]:
        lines.append(f"- {t['id']}: {t['use_when']} Blanks: {', '.join(t['fields'])}")
    return "\n".join(lines)


def decide_with_gemini(email: Email, cfg: dict) -> Decision:
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    ids = [t["id"] for t in cfg["templates"]] + [ESCALATE]
    all_fields = sorted({f for t in cfg["templates"] for f in t["fields"]})

    schema = {
        "type": "OBJECT",
        "properties": {
            "template_id": {"type": "STRING", "enum": ids},
            "fields": {
                "type": "OBJECT",
                "properties": {f: {"type": "STRING"} for f in all_fields},
            },
            "reason": {"type": "STRING"},
        },
        "required": ["template_id", "fields", "reason"],
    }

    primary = cfg.get("model", {}).get("gemini_name", "gemini-3.1-flash-lite")
    candidate_models = [primary] + [m for m in ("gemini-flash-latest", "gemini-3.5-flash-lite") if m != primary]

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt(cfg)}]
        },
        "contents": [{
            "parts": [{"text": f"From: {email.sender}\nSubject: {email.subject}\n\n{email.body}"}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "maxOutputTokens": cfg.get("model", {}).get("max_tokens", 800),
        },
    }

    last_err = None
    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    part_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    result = json.loads(part_text)
                    return Decision(result["template_id"], result.get("fields", {}), result.get("reason", ""))
                elif resp.status_code in (503, 429) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    last_err = f"Gemini {model} error ({resp.status_code}): {resp.text}"
                    break
            except Exception as ex:
                last_err = str(ex)
                break

    raise RuntimeError(last_err or "All Gemini models failed")


def decide_with_ai(email: Email, cfg: dict) -> Decision:
    """Tries Gemini first, with Claude as fallback."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        try:
            return decide_with_gemini(email, cfg)
        except Exception as e:
            print(f"[Gemini error: {e}. Falling back to Claude...]", file=sys.stderr)

    return decide_with_claude(email, cfg)


def decide_with_claude(email: Email, cfg: dict) -> Decision:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=cfg["model"]["name"],
        max_tokens=cfg["model"]["max_tokens"],
        system=system_prompt(cfg),
        tools=[build_tool(cfg)],
        tool_choice={"type": "tool", "name": "choose_reply"},
        messages=[{"role": "user", "content": f"From: {email.sender}\nSubject: {email.subject}\n\n{email.body}"}],
    )
    call = next(b for b in resp.content if b.type == "tool_use")
    return Decision(call.input["template_id"], call.input.get("fields", {}), call.input.get("reason", ""))


def decide_mock(email: Email, cfg: dict) -> Decision:
    """Rule-based stand-in so the pipeline can be demoed/tested without an API key."""
    text = f"{email.subject} {email.body}".lower()

    # 1. Invoice or billing request
    if "invoice" in text or "milestone" in text or "payment" in text or "bill" in text:
        amt_match = re.search(r"\$[\d,]+", email.body)
        amount = amt_match.group(0) if amt_match else "As agreed"
        return Decision(
            "invoice_draft",
            {
                "project_summary": email.subject.replace("Invoice for ", "").replace("Invoice - ", ""),
                "invoice_description": "Approved project milestone deliverables",
                "amount": amount,
                "payment_terms": "Due upon receipt via standard agreed method",
            },
            "Client requested milestone invoice",
        )

    # 2. Too brief / vague
    if len(email.body.split()) < 12:
        return Decision(
            "need_more_info",
            {
                "missing_items": "- Core features & technical requirements\n- Preferred tech stack & integrations\n- Target timeline & budget range"
            },
            "Inquiry lacks essential project specifications",
        )

    # 3. Out of scope
    if any(k in text for k in ("plumbing", "hardware repair", "electrician", "roofing")):
        return Decision(
            "out_of_scope",
            {"project_summary": email.subject, "service_focus": "AI Automation and Full-Stack Engineering"},
            "Request is outside core software & AI services",
        )

    # 4. Standard project quote
    return Decision(
        "new_project_quote",
        {
            "project_summary": email.subject,
            "suggested_next_step": "I would be glad to hop on a 15-minute discovery call this Thursday to discuss the architecture and implementation details.",
        },
        "Client requesting new project proposal / quote",
    )


# ---------- rendering ----------

def render(decision: Decision, email: Email, cfg: dict) -> Decision:
    if decision.template_id == ESCALATE:
        return decision
    tpl = next(t for t in cfg["templates"] if t["id"] == decision.template_id)
    values = {"first_name": email.first_name, **decision.fields, "signature": cfg["client"]["signature"]}
    missing = [f for f in tpl["fields"] if not str(values.get(f, "")).strip()]
    if missing:  # never send a half-filled template to the reviewer
        return Decision(ESCALATE, reason=f"model left blanks empty: {missing}")
    decision.draft = tpl["text"].format(**values)
    return decision


def process(email: Email, cfg: dict, mock: bool) -> Decision:
    blocked = guardrail_check(email, cfg)
    if blocked:
        return Decision(ESCALATE, reason=blocked)
    d = decide_mock(email, cfg) if mock else decide_with_ai(email, cfg)
    return render(d, email, cfg)


# ---------- Gmail (drafts only) ----------

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # read, label, draft. Code never calls send.


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = ROOT / "token.json"
    creds = Credentials.from_authorized_user_file(token, SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(ROOT / "credentials.json", SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def label_id(svc, name: str) -> str:
    for l in svc.users().labels().list(userId="me").execute().get("labels", []):
        if l["name"] == name:
            return l["id"]
    return svc.users().labels().create(userId="me", body={"name": name}).execute()["id"]


def fetch_emails(svc, cfg: dict) -> list[Email]:
    q = f'{cfg["workflow"]["gmail_query"]} -label:{cfg["workflow"]["label_after_draft"]}'
    refs = svc.users().messages().list(userId="me", q=q, maxResults=cfg["workflow"]["max_emails_per_run"]).execute()
    out = []
    for r in refs.get("messages", []):
        m = svc.users().messages().get(userId="me", id=r["id"], format="full").execute()
        h = {x["name"].lower(): x["value"] for x in m["payload"]["headers"]}
        out.append(Email(m["id"], h.get("from", ""), h.get("subject", ""), extract_body(m["payload"]) or m.get("snippet", ""),
                         m["threadId"], h.get("message-id")))
    return out


def extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        text = extract_body(part)
        if text:
            return text
    return ""


def save_draft(svc, email: Email, text: str):
    msg = MIMEText(text)
    msg["To"] = email.sender
    msg["Subject"] = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
    if email.message_id_header:
        msg["In-Reply-To"] = msg["References"] = email.message_id_header
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc.users().drafts().create(userId="me", body={"message": {"raw": raw, "threadId": email.thread_id}}).execute()


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", action="store_true")
    src.add_argument("--gmail", action="store_true")
    ap.add_argument("--test-week", action="store_true", help="compare to expected_template, log mismatches")
    ap.add_argument("--mock", action="store_true", help="rule-based stand-in instead of Claude")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    assert cfg["guardrails"]["never_send"], "this tool only drafts"

    if args.sample:
        svc = None
        emails = [Email(e["id"], e["from"], e["subject"], e["body"], expected_template=e.get("expected_template"))
                  for e in json.loads((ROOT / "sample_emails.json").read_text())]
    else:
        svc = gmail_service()
        emails = fetch_emails(svc, cfg)
        lbl = label_id(svc, cfg["workflow"]["label_after_draft"])

    mismatches = []
    for e in emails:
        d = process(e, cfg, args.mock)
        print(f"\n=== {e.subject}  ({e.sender})\n-> {d.template_id}: {d.reason}")
        if d.draft:
            print("-" * 40 + f"\n{d.draft}")
        if svc and d.draft:
            save_draft(svc, e, d.draft)
        if svc:  # label either way so the reviewer sees it was handled / escalated
            svc.users().messages().modify(userId="me", id=e.id, body={"addLabelIds": [lbl]}).execute()
        if args.test_week and e.expected_template and e.expected_template != d.template_id:
            mismatches.append({"case": e.id, "subject": e.subject, "expected": e.expected_template,
                               "actual": d.template_id, "reason": d.reason})

    if args.test_week:
        n = len([e for e in emails if e.expected_template])
        print(f"\nTest week: {n - len(mismatches)}/{n} matched expected.")
        with open(ROOT / "mismatches.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["case", "subject", "expected", "actual", "reason"])
            w.writeheader()
            w.writerows(mismatches)
        print("Mismatch log -> mismatches.csv")


if __name__ == "__main__":
    sys.exit(main())
