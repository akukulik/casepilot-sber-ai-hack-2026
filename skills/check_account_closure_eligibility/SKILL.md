---
name: check_account_closure_eligibility
description: Deterministically assess synthetic account closure eligibility from prior results.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 30
---

# Check Account Closure Eligibility

Read-only mock. An eligible result does not close the account.

Ouroboros 6.61.4 limits registered tool names to 24 characters, so the
technical registered alias is `closure_eligibility`; the canonical plan
action and Skill directory remain `check_account_closure_eligibility`.
