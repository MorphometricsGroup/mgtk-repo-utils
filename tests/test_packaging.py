# SPDX-License-Identifier: Apache-2.0
"""The constraints of design section 1 that a test can enforce, over the workspace."""

import ast
import tomllib
from importlib.metadata import entry_points

from mgtk_repo_utils import __version__
from mgtk_repo_utils.tool import GROUP, Tool, discover
from support import PACKAGES, REPO

SKIPPED = {".git", ".venv", ".pytest_cache", "__pycache__"}
CORE = "mgtk_repo_utils"
TOOL_PACKAGES = {
    "issues-view": "mgtk_repo_utils_issues_view",
    "freeze-lint": "mgtk_repo_utils_freeze_lint",
    "link-check": "mgtk_repo_utils_link_check",
    "clone": "mgtk_repo_utils_clone",
}


def sources():
    """Every Python source of the distributions (not the tests)."""
    found = sorted((REPO / "src").rglob("*.py")) + sorted(PACKAGES.rglob("*.py"))
    return [p for p in found if not SKIPPED & set(p.relative_to(REPO).parts)]


def pyprojects():
    return [REPO / "pyproject.toml", *sorted(PACKAGES.glob("*/pyproject.toml"))]


def imported_roots(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield (node.module or "").split(".")[0]


def test_every_source_file_starts_with_the_spdx_line():
    files = sources() + sorted((REPO / "tests").rglob("*.py"))
    assert files
    for path in files:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        # slug.py is a port of github-slugger and carries both licences on its first line.
        assert first.startswith("# SPDX-License-Identifier: Apache-2.0"), path


def test_source_text_has_no_section_sign_and_no_url():
    for path in sources():
        text = path.read_text(encoding="utf-8")
        assert "§" not in text, path
        assert "http://" not in text and "https://" not in text, path


def test_every_distribution_ships_the_licence():
    for path in pyprojects():
        assert (path.parent / "LICENSE").is_file(), path.parent
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["project"]["license"].startswith("Apache-2.0"), path


def test_every_distribution_carries_the_one_version():
    versions = {}
    for path in pyprojects():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        versions[data["project"]["name"]] = data["project"]["version"]
    assert set(versions.values()) == {__version__}, versions
    assert set(versions) == {
        "mgtk-repo-utils",
        "mgtk-repo-utils-core",
        *(f"mgtk-repo-utils-{name}" for name in TOOL_PACKAGES),
    }


def test_the_core_imports_no_tool_and_no_tool_imports_another():
    tool_packages = set(TOOL_PACKAGES.values())
    for path in sources():
        owner = path.relative_to(REPO).parts
        roots = set(imported_roots(path))
        if "core" in owner:
            assert not roots & tool_packages, (path, roots & tool_packages)
        else:
            own = {p for p in tool_packages if p in owner}
            foreign = (roots & tool_packages) - own
            assert not foreign, (path, foreign)


def test_every_entry_point_loads_a_tool_and_discovery_finds_them_all():
    points = list(entry_points(group=GROUP))
    assert {p.name for p in points} == {"issues-view", "freeze-lint", "link-check", "resolve", "clone"}
    tools = discover(points)
    assert all(isinstance(t, Tool) for t in tools.values())
    assert tools["resolve"].table is tools["clone"].table
    assert tools["clone"].check is None
    assert [t.name for t in sorted(tools.values(), key=lambda t: (t.check_order, t.name))] == [
        "issues-view",
        "freeze-lint",
        "link-check",
        "resolve",
        "clone",
    ]


def test_the_hook_manifest_names_a_hook_per_tool_and_check():
    import yaml

    hooks = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    by_id = {hook["id"]: hook for hook in hooks}
    assert set(by_id) == {
        "mgtk-repo-utils-issues-view",
        "mgtk-repo-utils-freeze-lint",
        "mgtk-repo-utils-link-check",
        "mgtk-repo-utils-check",
    }
    for hook_id, hook in by_id.items():
        assert hook["entry"] == "mgtk-repo-utils " + hook_id.removeprefix("mgtk-repo-utils-")
        assert hook["language"] == "python"
        assert hook["pass_filenames"] is False and hook["always_run"] is True


def test_every_tool_message_has_both_languages_and_no_section_sign():
    for tool in discover().values():
        assert tool.messages, tool.name
        for msg_id, pair in tool.messages.items():
            assert len(pair) == 2 and all(pair), (tool.name, msg_id)
            assert all("§" not in text for text in pair), (tool.name, msg_id)


def test_two_distributions_providing_one_tool_name_are_refused():
    import pytest

    from mgtk_repo_utils.report import ToolError

    points = list(entry_points(group=GROUP))
    twice = [p for p in points if p.name == "link-check"]
    with pytest.raises(ToolError) as info:
        discover(points + twice)
    assert "link-check" in str(info.value)
