---
name: openrouter_echo
description: Minimal proof-of-concept that sends one user string to the configured OpenRouter model and returns its answer.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool, route, net, read_settings]
env_from_settings: [OPENROUTER_API_KEY, OUROBOROS_MODEL]
when_to_use: Use only when validating that Ouroboros can run a reviewed Skill and call its configured OpenRouter model.
timeout_sec: 45
---

# OpenRouter Echo

This proof-of-concept accepts a non-empty text string, sends it to the
OpenRouter chat-completions endpoint using the provider key already configured
in Ouroboros Settings, and returns the model response.

The Skill never stores, prints, or returns the API key. It uses the model from
`OUROBOROS_MODEL`, limits input and output size, performs one request per call,
and has no retry loop.
