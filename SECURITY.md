# Security policy

This is an experimental loopback-only prototype, with no production release or support SLA. Only `main` is actively maintained.

Do not expose its port to the Internet, run customer code, or submit sensitive data. It accepts only fixed synthetic image statistics. It has no remote-user authentication, hostile-host isolation, or confidentiality guarantee against the computer owner.

## Private reporting

Use GitHub's [Report a vulnerability form](https://github.com/Andylaw95/community-ai-compute/security/advisories/new).

Include commit, synthetic reproduction steps, impact, and possible mitigation. Omit secrets/personal data. Keep exploitable details out of public issues while assessed. No guaranteed response time or bounty is offered.

General design questions and documented limitations belong in Discussions. See the [architecture](docs/ARCHITECTURE.md) for the trust model and known bottleneck.
