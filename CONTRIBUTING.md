# Contributing

CasePilot is a hackathon prototype. All examples and tests must remain fully
synthetic and must not contain bank, employee, or customer secrets.

## Local checks

1. Create and activate a virtual environment.
2. Install `requirements-dev.txt`.
3. Run `python scripts/run_tests.py`.
4. Run a secret scan before committing.

Changes to a Skill alter its Ouroboros content hash. Reinstall the Skills and
repeat review, grants, enablement, and preflight before an integration demo.

Runtime files, imports, generated artifacts, local locators, credentials, and
Ouroboros settings must never be committed.
