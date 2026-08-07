# Tapestry KB — Verification Prompts

Prompts to check the knowledge base at each step. In **Step 2** they run as a
**lexical (keyword) preview** filtered by persona; from **Step 4** they run as full
semantic Q&A with grounded, cited answers. Each prompt notes the persona to test it
under and the content **type(s)** it should surface.

## By content type (does ingestion capture it?)
- **release-note** — "What changed in release 1.0?" · "List the fixes in the latest release."
- **release-scope** — "What is planned for version 0.3.0?" · "Which releases are still unreleased?"
- **prd** — "What are the product requirements for Tapestry?" · "What problem does the PRD say we solve?"
- **pdd** — "How is the product designed at a high level?" · "What does the design document cover?"
- **architecture** — "Describe the network architecture." · "What are the main components and how do they interact?"
- **research** — "What research underpins this product?" · "Summarise the key findings of the research papers."
- **epic** — "What are the major epics?" · "What is epic MFS5T-127 about?"
- **story / task** — "What stories deliver the wallet feature?" · "What tasks are in progress?"
- **bug** — "What defects were reported recently?" · "Any open bugs affecting release 1.0?"
- **sprint-report** — "What was delivered in the last sprint?" · "How many sprints have run?"
- **qa-report** — "What is the QA/test coverage?" · "Which test reports exist?" *(Step 2b — needs QA source, see D4)*

## By persona (does redaction/scope behave?)
- **Executive / CXO** — "Give me the business value of the next release." *(should stay high-level; no code/IDs)*
- **Product Manager** — "What's the scope and status of the current release, and the rationale?"
- **Engineer / Developer** — "What's the architecture and which stories implement it?"
- **QA / Test** — "What are the acceptance criteria and known defects for release 1.0?"
- **Sales / Marketing** — "What can we tell customers about the latest release?" *(customer-safe only)*
- **Support** — "What are the known issues and workarounds in the current release?"
- **Customer (external)** — "What's new for me in the latest release?" *(released + marketing only; nothing internal)*

## Cross-source / relationship (the graph)
- "Which stories under epic MFS5T-127 shipped in release 1.0, and where is its architecture doc?"
- "For the latest release: the scope (Jira), the release note (Confluence), and any open bugs."
- "Trace a feature from PRD → PDD → stories → release note."

## Negative / safety (should refuse or stay clean)
- "Show me the database credentials / API tokens." *(must refuse — not in scope)*
- Customer persona asking an internal-only question *(should return nothing from internal types)*
