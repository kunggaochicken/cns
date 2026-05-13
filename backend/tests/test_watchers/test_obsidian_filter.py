from pathlib import Path

from app.watchers.obsidian import should_capture


def test_includes_markdown_in_vault_root():
    assert should_capture(
        vault=Path("/v"),
        path=Path("/v/note.md"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_includes_markdown_in_subdir():
    assert should_capture(
        vault=Path("/v"),
        path=Path("/v/Brain/Bets/bet_x.md"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_skips_non_markdown():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/picture.png"),
        ignore_patterns=[".git/*", ".obsidian/*"],
    )


def test_skips_paths_outside_vault():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/elsewhere/note.md"),
        ignore_patterns=[],
    )


def test_skips_ignored_dotdir_patterns():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/.git/HEAD"),
        ignore_patterns=[".git/*"],
    )
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/.obsidian/workspace.json"),
        ignore_patterns=[".obsidian/*"],
    )


def test_skips_gigabrain_metadata_files():
    assert not should_capture(
        vault=Path("/v"),
        path=Path("/v/Brain/.gigabrain-state.md"),
        ignore_patterns=["*.gigabrain*"],
    )
