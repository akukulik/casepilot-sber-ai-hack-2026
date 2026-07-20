---
name: find_case_scenarios
description: Retrieve up to three approved CasePilot resolution scenarios for a validation case using topic/subtopic filtering, BM25, business reranking, required-input coverage, and historical evidence.
version: 0.1.0
type: script
runtime: python3
scripts:
  - name: find_case_scenarios.py
    description: Rank approved scenarios for one validation-case JSON object.
permissions: []
when_to_use: Use inside take_case after loading a case and before building a plan.
timeout_sec: 20
---

# Find Case Scenarios

Pass a validation-case object in `--case-json`. The result contains up to three
approved scenarios, their scores, explanations, and resolved source historical
cases. Only approved catalog entries participate.

Retrieval filters by exact topic/subtopic, applies BM25 over the scenario card,
then reranks by closure code, product overlap, required-input coverage, success
rate, and approval status. Fallback is topic-only, then all approved scenarios.

