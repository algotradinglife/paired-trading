# Research OS contribution contract

This repository uses colocated Jujutsu workspaces. The role directories are not Git
worktrees: running `git` in a role directory can resolve to the parent checkout and mutate
its `main` working copy. Use `jj` for status, history, bookmark movement, and push.

## Role identity and integration flow

| Public role | Agent Deck dispatcher alias | Jujutsu workspace | Active bookmark | PR base |
| --- | --- | --- | --- | --- |
| `PT-Engineer` | `paired-trading-Engineer` | `develop` | `develop` | `main` |
| `PT-Strategy` | `paired-trading-Strategy` | `strategy-active` | `strategy/active` | `develop` |
| `PT-Data` | `paired-trading-Data` | `data-active` | `data/active` | `develop` |

The public names are routing roles. Agent Deck dispatches to the aliases in the second
column. The contribution path is always:

```text
strategy/active or data/active -> develop
develop -> main
```

Feature, research, and data work therefore integrate through `develop`; only the Engineer
integration bookmark opens a PR to `main`.

## Mandatory preflight

Run the preflight from the dispatched role directory before editing any file:

```bash
src/scripts/research_os_preflight.sh PT-Engineer
src/scripts/research_os_preflight.sh PT-Strategy
src/scripts/research_os_preflight.sh PT-Data
```

The corresponding Agent Deck alias is also accepted. The command fails closed unless all
of these statements are true:

1. the current directory belongs to the mapped Jujutsu workspace;
2. `@` is an empty, clean task-start change;
3. the mapped bookmark is either on `@` or its direct parent, and no different bookmark is
   attached to `@`;
4. `@-` equals the current PR-base remote bookmark (`main@origin` for Engineer,
   `develop@origin` for Strategy and Data);
5. the role bookmark at `origin` equals that same shared baseline;
6. `origin` is `github.com/algotradinglife/paired-trading`;
7. the mapped PR target exists as a remote bookmark.

The preflight is a verifier, not a repair command. If it fails, stop and have the
dispatcher or integration owner reconcile the workspace. Do not switch to Git, rewrite
another role's bookmark, restore parent-checkout files, or delete a workspace.

## Claim, change, push, and PR

Claim a `state/ready` issue by assigning the dispatched GitHub identity. There is no
`state/in-progress` label, so `state/ready` remains until review handoff.

After preflight:

1. Make only the issue-scoped edits in the role workspace.
2. Inspect `jj status` and `jj diff`; Jujutsu snapshots files without a staging step.
3. Describe the task change with `jj describe -m "<terse summary>"`.
4. Move the mapped role bookmark explicitly with
   `jj bookmark set <role-bookmark> -r @`.
5. Push only that bookmark with `jj git push --bookmark <role-bookmark>`.
6. Open the mapped PR and include the issue link, impact, and validation.
7. Create a clean placeholder with `jj new <role-bookmark>` while the PR is reviewed.

Never use `git add`, `git commit`, `git branch`, or `git push` from a role workspace.
Never use a broad cleanup command against the parent checkout.

## Lifecycle labels

The normal issue transition is:

```text
state/ready -> state/review -> state/reviewing -> state/completed
```

- `state/ready`: dispatched and claimable; assignment records the active owner.
- `state/review`: implementation and validation are complete and the PR is open.
- `state/reviewing`: a reviewer is actively evaluating the PR.
- `state/completed`: the PR is merged and post-merge cleanup is complete.
- `state/blocked`: progress needs an external decision, dependency, or access change.
- `state/cancelled`: the issue will not proceed.

`state/awaiting-review` is reserved for dispatcher-managed queues. For Research OS
engineering handoff, use `state/review` as required by the issue contract.

Only one `state/*` label should be present. Preserve the owner, domain, and type labels
when replacing the lifecycle label.

## Post-merge cleanup

The integration owner performs cleanup only after the PR is merged:

1. Fetch with `jj git fetch --remote origin`.
2. Verify the current `@` is the empty placeholder created after push.
3. Advance the role bookmark to the merged shared baseline:
   - Engineer: `jj bookmark set develop -r main@origin`
   - Strategy: `jj bookmark set strategy/active -r develop@origin`
   - Data: `jj bookmark set data/active -r develop@origin`
4. Push only that bookmark so its remote target matches the shared baseline.
5. Rebase the empty placeholder onto the reset bookmark:
   `jj rebase -s @ -d <role-bookmark>`.
6. Run the role preflight again before dispatching another task.

If `@` is not empty at cleanup time, stop. It may contain another contributor's work and
must not be abandoned, restored, or rebased as part of cleanup.
