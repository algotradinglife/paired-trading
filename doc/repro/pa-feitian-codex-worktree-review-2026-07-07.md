# PA / Feitian Codex Worktree Review Packet

Date: 2026-07-07
Repo: `git@github.com:algotradinglife/paired-trading.git`
Project root: `/home/drwho1985/workspace/quant/strats/paired-trading`

## Purpose

This packet is for design review before the `strategy` and `frontend` Codex
sessions start implementation work. The intent is to make the local
coordination state visible through git so another reviewer can reason about
the branch model, worktree layout, merge path, and sequencing.

## Current Git State

Remote branches already pushed:

```text
origin/main                            cd4d6fc03e82a4493a38719c5a2b8e488de124e0
origin/baseline/paired-trading-v01     50b3cf92f4058f4fcaf521784600bbd5a55cf8ab
origin/strategy/pa-feitian-v02         50b3cf92f4058f4fcaf521784600bbd5a55cf8ab
origin/frontend/pa-feitian-dashboard   50b3cf92f4058f4fcaf521784600bbd5a55cf8ab
```

The baseline commit is ahead of `origin/main`; `origin/main` is an ancestor of
`50b3cf92f4058f4fcaf521784600bbd5a55cf8ab`.

Local branches:

```text
baseline/paired-trading-v01
strategy/pa-feitian-v02
frontend/pa-feitian-dashboard
coordination/pa-feitian-design-review
```

## Worktree Layout

The project root is the baseline/reference surface:

```text
/home/drwho1985/workspace/quant/strats/paired-trading
```

Long-running Codex sessions work only inside project-local worktrees:

```text
/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/strategy
/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/frontend
/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/coordination
```

Branch to session mapping:

```text
strategy-session     -> strategy/pa-feitian-v02
frontend-session     -> frontend/pa-feitian-dashboard
coordination-session -> coordination/pa-feitian-design-review
```

`.worktrees/` is excluded locally via `.git/info/exclude`, not committed.

## Hermes Board State

Hermes board: `paired-trading`

Implementation cards:

```text
t_b243af53  STRAT-001 PA/Feitian strategy worktree session
  assignee: strategy-session
  branch: strategy/pa-feitian-v02
  worktree: .worktrees/strategy

t_d6529a6a  FE-001 PA/Feitian frontend worktree session
  assignee: frontend-session
  branch: frontend/pa-feitian-dashboard
  worktree: .worktrees/frontend
```

Recommended state while this packet is under review: both implementation cards
should remain parked rather than starting business logic changes.

## Proposed Sequencing

1. Review this coordination packet.
2. Decide whether the branch/worktree/session model is sufficient.
3. If accepted, let `strategy-session` claim `t_b243af53`.
4. Let `frontend-session` claim `t_d6529a6a` only after it has a clear data/API
   contract to consume, or keep it focused on shell/UI scaffolding.
5. Use a shared/integration branch only when a contract crosses the strategy
   and frontend boundary.

## Proposed Merge Model

Conservative merge path:

```text
baseline/paired-trading-v01
    -> strategy/pa-feitian-v02
    -> frontend/pa-feitian-dashboard
    -> integration/pa-feitian-v02
    -> main
```

Shared contract changes should be isolated into a short-lived branch:

```text
shared/pa-feitian-contract-*
```

Then fast-forward or merge that shared branch into both `strategy` and
`frontend` before either branch builds on the contract.

## Design Questions For Review

1. Should `50b3cf9` remain the baseline anchor, or should it first be promoted
   into `main` before implementation branches move?
2. Should `frontend` begin now with a static/dashboard shell, or wait until
   `strategy` produces a stable PA/Feitian data-access contract inside this
   repo?
3. Should shared contracts live under `src/engine`, `src/tools`, `doc/schemas`,
   or a new explicit package/module boundary?
4. Should Hermes cards be split into smaller tasks before implementation, for
   example:
   - strategy data contract
   - strategy feature/scoring layer
   - strategy validation harness
   - frontend data loader
   - frontend dashboard shell
   - frontend packet drill-down
5. What should be the first integration milestone that proves strategy and
   frontend are aligned?

## Current Recommendation

Do not start broad implementation yet. The repo is ready for branch-separated
work, but the next high-leverage step is a small shared contract design:

```text
strategy produces a minimal, file-backed PA/Feitian snapshot API
frontend consumes only that API and renders a read-only dashboard shell
```

Only after that contract is reviewed should the two sessions branch into deeper
strategy quantification and richer frontend interaction work.
