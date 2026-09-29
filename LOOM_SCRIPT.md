# 60–90 second Loom script

**0:00 – Hook (show config.yaml)**
"This is a Gmail reply drafter I built with Claude. Everything client-specific lives in this one config file: their templates, service area and guardrails. A new client means a new config, not new code."

**0:15 – The templates**
"These are the client's own replies. Claude never rewrites them. It only picks one and fills in the blanks, through a forced tool call, so the output is always structured."

**0:25 – Run it (terminal: `python drafter.py --sample --test-week`)**
"Four real-looking emails. A quote request gets the quote template. A vague one asks for details. An out-of-area one gets a polite no. And this one, about an invoice refund to a new bank account, gets escalated. It never reaches the model, because money and bank emails are blocked by a hard rule."

**0:50 – Gmail (optional: show the Drafts folder after `--gmail`)**
"On a real inbox it only creates drafts and adds a label. Nothing gets sent. A person reviews and sends every one."

**1:05 – Test week**
"Test-week mode checks decisions against known cases and logs every mismatch to a CSV, so a reviewer can go through it in minutes."

**1:15 – Close**
"Config-driven, the client's own voice, humans send, and every mismatch is logged. That's how I'd approach your installs."
