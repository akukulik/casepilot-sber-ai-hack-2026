---
name: check_account_state
description: Return deterministic synthetic account state for an approved CasePilot case.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 30
---

# Check Account State

Read-only mock. It never connects to a bank or changes a product.
