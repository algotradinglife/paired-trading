#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_GITHUB_REPOSITORY="algotradinglife/paired-trading"

usage() {
    cat <<'EOF'
Usage: src/scripts/research_os_preflight.sh ROLE

ROLE must be one of the public Research OS roles or its Agent Deck alias:
  PT-Engineer | paired-trading-Engineer
  PT-Strategy | paired-trading-Strategy
  PT-Data     | paired-trading-Data
EOF
}

fail() {
    printf 'Research OS preflight: FAIL: %s\n' "$*" >&2
    exit 1
}

resolve_one_commit() {
    local revset="$1"
    local commit

    if ! commit=$(jj log -r "$revset" --no-graph -T 'commit_id ++ "\n"' 2>/dev/null); then
        fail "cannot resolve required revision '$revset'"
    fi
    if [[ -z "$commit" || "$commit" == *$'\n'* ]]; then
        fail "revision '$revset' must resolve to exactly one commit"
    fi
    printf '%s' "$commit"
}

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 64
fi

case "$1" in
    PT-Engineer | paired-trading-Engineer)
        public_role="PT-Engineer"
        dispatcher_alias="paired-trading-Engineer"
        expected_workspace="develop"
        expected_bookmark="develop"
        pr_base="main"
        ;;
    PT-Strategy | paired-trading-Strategy)
        public_role="PT-Strategy"
        dispatcher_alias="paired-trading-Strategy"
        expected_workspace="strategy-active"
        expected_bookmark="strategy/active"
        pr_base="develop"
        ;;
    PT-Data | paired-trading-Data)
        public_role="PT-Data"
        dispatcher_alias="paired-trading-Data"
        expected_workspace="data-active"
        expected_bookmark="data/active"
        pr_base="develop"
        ;;
    *)
        usage >&2
        fail "unknown role '$1'"
        ;;
esac

command -v jj >/dev/null 2>&1 || fail "jj is not installed or not on PATH"

if ! workspace_root=$(jj workspace root 2>/dev/null); then
    fail "current directory is not inside a Jujutsu workspace"
fi

if ! workspace_rows=$(
    jj workspace list -T 'self.name() ++ "\t" ++ self.root() ++ "\n"' 2>/dev/null
); then
    fail "cannot list Jujutsu workspaces"
fi

workspace_name=""
workspace_matches=0
while IFS=$'\t' read -r candidate_name candidate_root; do
    if [[ "$candidate_root" == "$workspace_root" ]]; then
        workspace_name="$candidate_name"
        workspace_matches=$((workspace_matches + 1))
    fi
done <<<"$workspace_rows"

if [[ "$workspace_matches" -ne 1 ]]; then
    fail "could not identify exactly one workspace for root '$workspace_root'"
fi
if [[ "$workspace_name" != "$expected_workspace" ]]; then
    fail "role $public_role requires workspace '$expected_workspace', found '$workspace_name'"
fi

# This snapshots the working copy before evaluating whether the task starts clean.
if ! working_copy_empty=$(
    jj log -r '@' --no-graph -T 'if(empty, "true", "false") ++ "\n"' 2>/dev/null
); then
    fail "cannot inspect the Jujutsu working copy"
fi
if [[ "$working_copy_empty" != "true" ]]; then
    fail "working copy @ is not empty; preserve or finish existing work before task start"
fi

working_copy_commit=$(resolve_one_commit '@')
parent_commit=$(resolve_one_commit 'parents(@)')
bookmark_commit=$(resolve_one_commit "$expected_bookmark")
role_remote_commit=$(resolve_one_commit "$expected_bookmark@origin")
baseline_commit=$(resolve_one_commit "$pr_base@origin")

if ! working_copy_bookmarks=$(
    jj log -r '@' --no-graph \
        -T 'local_bookmarks.map(|bookmark| bookmark.name()).join("\n") ++ "\n"' \
        2>/dev/null
); then
    fail "cannot inspect bookmarks on the working copy"
fi

if [[ "$bookmark_commit" == "$working_copy_commit" ]]; then
    if [[ "$working_copy_bookmarks" != "$expected_bookmark" ]]; then
        fail "working copy must carry only bookmark '$expected_bookmark'"
    fi
elif [[ "$bookmark_commit" == "$parent_commit" ]]; then
    if [[ -n "$working_copy_bookmarks" ]]; then
        fail "empty working copy above '$expected_bookmark' must not carry another bookmark"
    fi
else
    fail "bookmark '$expected_bookmark' must point to @ or its direct parent"
fi

if [[ "$parent_commit" != "$baseline_commit" ]]; then
    fail "parent @- is not based on the shared '$pr_base@origin' baseline"
fi
if [[ "$role_remote_commit" != "$baseline_commit" ]]; then
    fail "'$expected_bookmark@origin' is not synchronized with '$pr_base@origin'"
fi

if ! remote_rows=$(jj git remote list 2>/dev/null); then
    fail "cannot list Jujutsu Git remotes"
fi

origin_url=""
origin_matches=0
while read -r remote_name remote_url extra; do
    if [[ "$remote_name" == "origin" ]]; then
        [[ -z "${extra:-}" ]] || fail "origin remote URL contains unexpected fields"
        origin_url="$remote_url"
        origin_matches=$((origin_matches + 1))
    fi
done <<<"$remote_rows"

if [[ "$origin_matches" -ne 1 ]]; then
    fail "expected exactly one Git remote named 'origin'"
fi

case "$origin_url" in
    "git@github.com:${EXPECTED_GITHUB_REPOSITORY}" \
    | "git@github.com:${EXPECTED_GITHUB_REPOSITORY}.git" \
    | "ssh://git@github.com/${EXPECTED_GITHUB_REPOSITORY}" \
    | "ssh://git@github.com/${EXPECTED_GITHUB_REPOSITORY}.git" \
    | "https://github.com/${EXPECTED_GITHUB_REPOSITORY}" \
    | "https://github.com/${EXPECTED_GITHUB_REPOSITORY}.git")
        ;;
    *)
        fail "origin must be GitHub repository '$EXPECTED_GITHUB_REPOSITORY', found '$origin_url'"
        ;;
esac

printf '%s\n' \
    "Research OS preflight: PASS" \
    "  public role:      $public_role" \
    "  dispatcher alias: $dispatcher_alias" \
    "  workspace:        $workspace_name" \
    "  active bookmark:  $expected_bookmark" \
    "  shared baseline:  $pr_base@origin ($baseline_commit)" \
    "  GitHub origin:    $EXPECTED_GITHUB_REPOSITORY" \
    "  PR flow:          $expected_bookmark -> $pr_base"
