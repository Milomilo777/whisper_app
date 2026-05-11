# Integrations

Notes and briefs for interoperating with third-party tools. Each integration has at minimum a **research** note (what the third-party tool is, what its file format / API looks like, design constraints) and an **implementation brief** (the scope, acceptance criteria, and constraints for an autonomous Claude Code session).

The pattern is the same for every integration:

1. A research note answers: *what is this thing, what does it accept and produce, what are the constraints and traps, what are the open questions*. Written before any code.
2. A brief turns the research into actionable scope for a single hands-off implementation session: tasks, tests, acceptance plan, push policy.
3. The implementation lands on `master`. The brief is preserved for history — never deleted.
4. When the work is shipped, an `<integration>-acceptance.md` is added next to the brief, holding the machine-parseable acceptance test plan.

## Index

| Integration | Status | Research | Brief | Acceptance |
|---|---|---|---|---|
| oTranscribe (web app for manual transcription) | brief written, not implemented | [otranscribe-research.md](otranscribe-research.md) | [otranscribe-brief.md](otranscribe-brief.md) | _coming with implementation_ |

## How to add a new integration

1. Create `docs/integrations/<name>-research.md`. Cover: what the tool is, its license and source URL, file formats consumed and produced, schemas, any quirks discovered, three-tier integration plan (MVP / nice-to-have / power), open questions for the user, sources cited.
2. Create `docs/integrations/<name>-brief.md` modeled on [otranscribe-brief.md](otranscribe-brief.md). Cover: scope, public API, UI changes, tests, documentation, acceptance plan, hands-off policy, constraints, known traps, source files to glance at, push policy.
3. Append a row to the index above.
4. When implementation lands, add `docs/integrations/<name>-acceptance.md` and update the row's Status.

This keeps every cross-tool design decision recoverable from the repository alone. No external context required.
