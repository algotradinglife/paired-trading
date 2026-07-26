from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research_os_preflight.sh"
ROLE_CASES = [
    ("PT-Engineer", "develop", "develop", "main"),
    ("PT-Strategy", "strategy-active", "strategy/active", "develop"),
    ("PT-Data", "data-active", "data/active", "develop"),
]


def _write_fake_jj(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_jj = fake_bin / "jj"
    fake_jj.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import sys

            args = sys.argv[1:]

            if args[:2] == ["workspace", "root"]:
                print(os.environ["FAKE_ROOT"])
            elif args[:2] == ["workspace", "list"]:
                print(f'{os.environ["FAKE_WORKSPACE"]}\\t{os.environ["FAKE_ROOT"]}')
                print(f'other-workspace\\t{os.environ["FAKE_ROOT"]}-other')
            elif args[:3] == ["git", "remote", "list"]:
                print(f'origin {os.environ["FAKE_ORIGIN"]}')
            elif args and args[0] == "log":
                revset = args[args.index("-r") + 1]
                template = args[args.index("-T") + 1]
                if revset == "@" and "if(empty" in template:
                    print(os.environ["FAKE_EMPTY"])
                elif revset == "@" and "local_bookmarks" in template:
                    print(os.environ["FAKE_WORKING_COPY_BOOKMARKS"])
                elif revset == "@":
                    print(os.environ["FAKE_WORKING_COPY_COMMIT"])
                elif revset == "parents(@)":
                    print(os.environ["FAKE_PARENT_COMMIT"])
                elif revset == os.environ["FAKE_BOOKMARK"]:
                    print(os.environ["FAKE_BOOKMARK_COMMIT"])
                elif revset == f'{os.environ["FAKE_BOOKMARK"]}@origin':
                    print(os.environ["FAKE_ROLE_REMOTE_COMMIT"])
                elif revset == f'{os.environ["FAKE_PR_BASE"]}@origin':
                    print(os.environ["FAKE_BASELINE_COMMIT"])
                else:
                    print(f"unknown fake revset: {revset}", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"unsupported fake jj invocation: {args}", file=sys.stderr)
                sys.exit(1)
            """
        )
    )
    fake_jj.chmod(0o755)
    return fake_bin


def _run_preflight(
    tmp_path: Path,
    role: str,
    workspace: str,
    bookmark: str,
    pr_base: str,
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    fake_bin = _write_fake_jj(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "FAKE_ROOT": str(workspace_root),
            "FAKE_WORKSPACE": workspace,
            "FAKE_BOOKMARK": bookmark,
            "FAKE_PR_BASE": pr_base,
            "FAKE_EMPTY": "true",
            "FAKE_WORKING_COPY_COMMIT": "working-copy-commit",
            "FAKE_PARENT_COMMIT": "shared-baseline-commit",
            "FAKE_BOOKMARK_COMMIT": "working-copy-commit",
            "FAKE_ROLE_REMOTE_COMMIT": "shared-baseline-commit",
            "FAKE_BASELINE_COMMIT": "shared-baseline-commit",
            "FAKE_WORKING_COPY_BOOKMARKS": bookmark,
            "FAKE_ORIGIN": "git@github.com:algotradinglife/paired-trading.git",
        }
    )
    env.update(overrides)
    return subprocess.run(
        [str(SCRIPT), role],
        cwd=workspace_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(("role", "workspace", "bookmark", "pr_base"), ROLE_CASES)
def test_preflight_passes_for_each_role_mapping(
    tmp_path: Path,
    role: str,
    workspace: str,
    bookmark: str,
    pr_base: str,
) -> None:
    result = _run_preflight(tmp_path, role, workspace, bookmark, pr_base)

    assert result.returncode == 0, result.stderr
    assert "Research OS preflight: PASS" in result.stdout
    assert f"workspace:        {workspace}" in result.stdout
    assert f"PR flow:          {bookmark} -> {pr_base}" in result.stdout


def test_preflight_accepts_agent_deck_alias_and_clean_child_change(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "paired-trading-Engineer",
        "develop",
        "develop",
        "main",
        FAKE_BOOKMARK_COMMIT="shared-baseline-commit",
        FAKE_WORKING_COPY_BOOKMARKS="",
    )

    assert result.returncode == 0, result.stderr
    assert "dispatcher alias: paired-trading-Engineer" in result.stdout


def test_preflight_fails_closed_in_wrong_workspace(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "PT-Engineer",
        "strategy-active",
        "develop",
        "main",
    )

    assert result.returncode == 1
    assert "requires workspace 'develop', found 'strategy-active'" in result.stderr


def test_preflight_fails_closed_on_wrong_active_bookmark(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "PT-Engineer",
        "develop",
        "develop",
        "main",
        FAKE_BOOKMARK_COMMIT="shared-baseline-commit",
        FAKE_WORKING_COPY_BOOKMARKS="feature/unrelated",
    )

    assert result.returncode == 1
    assert "must not carry another bookmark" in result.stderr


def test_preflight_fails_closed_on_dirty_working_copy(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "PT-Engineer",
        "develop",
        "develop",
        "main",
        FAKE_EMPTY="false",
    )

    assert result.returncode == 1
    assert "working copy @ is not empty" in result.stderr


def test_preflight_fails_closed_on_stale_parent(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "PT-Data",
        "data-active",
        "data/active",
        "develop",
        FAKE_PARENT_COMMIT="stale-parent-commit",
    )

    assert result.returncode == 1
    assert "is not based on the shared 'develop@origin' baseline" in result.stderr


def test_preflight_fails_closed_on_wrong_github_remote(tmp_path: Path) -> None:
    result = _run_preflight(
        tmp_path,
        "PT-Strategy",
        "strategy-active",
        "strategy/active",
        "develop",
        FAKE_ORIGIN="git@github.com:someone-else/paired-trading.git",
    )

    assert result.returncode == 1
    assert "origin must be GitHub repository 'algotradinglife/paired-trading'" in result.stderr
