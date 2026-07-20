---
name: build_resolution_recommendation
description: Build and persist an evidence-bound CasePilot recommendation after one approved plan reaches a terminal execution status.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool, net, read_settings]
env_from_settings: [OPENROUTER_API_KEY]
dependencies: [jsonschema]
when_to_use: Use once after execute_approved_plan returns completed, waiting_for_information, replan_required, manual_review, or failed.
timeout_sec: 180
---

# Build Resolution Recommendation

Call `build_resolution_rec` with the terminal `execution_id`.

The tool loads the matching case, approved plan, and execution from CasePilot
runtime. It asks `z-ai/glm-5.2` for one structured Russian recommendation and
validates every finding against an actual completed step and `result_code`.
One repair request is allowed. If the provider is unavailable or both responses
are invalid, store a deterministic safe fallback.

Never claim that a banking operation or client communication was performed.
Always leave the final decision to `EMP-DEMO-001`. Return the recommendation,
its runtime identity, model metadata, and whether the fallback was used.
