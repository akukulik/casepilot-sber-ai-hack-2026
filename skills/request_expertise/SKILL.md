---
name: request_expertise
description: Run a catalog-bound deterministic synthetic expertise approved in a CasePilot plan.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 30
---

# Request Expertise

The expertise must exist in the catalog, be present in the approved plan, and
receive every catalog-required input. No external calls are made.
