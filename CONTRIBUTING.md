# Contributing

Welcome. We want broader access to useful compute, starting with evidence of what works. English and Traditional Chinese are welcome. Testing, documentation, accessibility, use cases, and criticism are as valuable as code.

## Start small

1. Read the [README](README.md) and [boundaries](docs/ARCHITECTURE.md).
2. Run `python3 -m examples.quickstart` on macOS or Linux with Python 3.12.
3. Pick a [good first issue](https://github.com/Andylaw95/community-ai-compute/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22), report a reproducible defect, or join [Discussions](https://github.com/Andylaw95/community-ai-compute/discussions).

Discuss substantial changes first: describe the problem, alternatives, trust assumptions, and success criteria. Reusing another project is welcome. Comment on a task before starting a large change to help coordinate effort.

## Pull requests

Fork, create a branch, and open a focused PR with the problem, behavior, verification, and limits. Keep the runtime dependency-free unless a concrete tradeoff has been discussed.

```bash
python3 -m unittest discover -s tests -v
python3 -m examples.quickstart
```

Use focused tests for changed behavior, especially leases, acceptance, replay, and cleanup. Do not label simulations as hardware tests. UI changes should include a browser check and screenshot; optional `tests/browser_check.py` needs separately installed Playwright/Chromium and a server on port 8765.

Exclude databases, credentials, private data, downloaded papers, and model weights. Use tiny synthetic or appropriately licensed fixtures. Do not broaden network exposure as a quick fix.

## Reproduction reports

Include commit, OS, architecture, Python version, command, expected/actual result, and redacted output. Local timing is not a GPU/network/cost benchmark. Personal contact details are unnecessary.

## AI assistance and license

Disclose material AI assistance. Contributors remain responsible for understanding changes, checking correctness/licensing, and giving honest evidence. The initial prototype and community materials were prepared with OpenAI Codex assistance.

Contributions intentionally submitted for inclusion follow [Apache-2.0](LICENSE). Only share material you have permission to contribute. No contributor agreement or payment commitment is currently offered.

Follow the [code of conduct](CODE_OF_CONDUCT.md). Report exploitable vulnerabilities [privately](SECURITY.md).
