# 60–90 second Loom script: AI Email & Invoice Reply Drafter

**0:00 – Hook (show config.yaml)**
"This is an automated Gmail reply and invoice drafter I built using structured AI generation. Everything runs from this single config file: my services, reply templates, signature, and security guardrails. It never sends anything on its own — human approval is built directly into the workflow."

**0:15 – The templates & human approval**
"The system uses structured templates for project quotes, invoice drafts, and scope clarifications. When a client requests an invoice or milestone billing, the AI extracts the milestone and amount, drafts the response, and places it directly into my Gmail drafts for my review and approval before anything leaves the inbox."

**0:30 – Run it (terminal: `python drafter.py --sample --test-week`)**
"Let's run it against four real-world client scenarios.
1. A technical inquiry gets an immediate proposal draft with an invitation to a discovery call.
2. A vague request prompts for specific architecture and budget details.
3. An approved milestone request drafts the exact invoice breakdown with terms.
4. And a suspicious email requesting an urgent wire transfer bank change is stopped immediately by the security guardrail without ever touching the model."

**0:55 – Gmail Inbox & Drafts (show Gmail Drafts with `AI-Drafted`)**
"When run on live Gmail with `--gmail`, it attaches to the existing email thread, generates a complete draft, and tags the message with an `AI-Drafted` label. All I do is open Gmail, review the numbers or proposal, and click Send."

**1:15 – Close**
"Deterministic security guardrails, structured AI drafting for proposals and invoices, and 100% human-in-the-loop approval. That ensures speed without sacrificing accuracy or control."
