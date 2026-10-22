# ChatGPT ↔ Claude Code handoff protocol

## Purpose
Use ChatGPT for strategy, independent challenge, and prioritization; use Claude Code for local repository inspection, implementation, and tests. This is a mediated workflow unless a real shared integration is configured. Do not assume the models can message each other directly.

## Every cycle
1. ChatGPT defines the decision/problem and acceptance criteria.
2. Owner opens the repository in Claude Code and asks Claude to follow `CLAUDE_CODE_START_HERE.md`.
3. Claude changes files locally, tests, and updates `docs/CLAUDE_HANDOFF.md`.
4. Owner pastes or uploads the handoff/diff to ChatGPT.
5. ChatGPT reviews strategy, economics, risk, and implementation claims; it returns specific corrections and next tasks.
6. Claude applies accepted corrections, runs tests, and reports evidence.

## Rules
- Keep each cycle small and verifiable.
- Separate hypotheses from observed customer behavior.
- No paid spend, customer outreach, production deployment, or legal/financial commitments without explicit owner approval.
- Record actual revenue, costs, delivery time, reply rates, conversion, and refunds; do not optimize vanity metrics.
- If there is no evidence of willingness to pay, change the offer before adding more features.
