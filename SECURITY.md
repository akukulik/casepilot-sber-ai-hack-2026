# Security

CasePilot is a synthetic demonstration and is not approved for production or
for processing real customer data.

- Never commit API keys, `.env`, Ouroboros settings, logs, or runtime traces.
- Never replace mock actions with write access to banking systems without
  authentication, authorization, allow-listed operations, audit, and
  human-in-the-loop review.
- Report a suspected secret leak privately to the repository owner. Revoke
  the affected credential immediately and remove it from Git history.
- The application binds to `127.0.0.1` by default and has no production
  authentication layer.
