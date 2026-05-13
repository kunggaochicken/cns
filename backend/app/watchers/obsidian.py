import fnmatch
from pathlib import Path


def should_capture(
    *,
    vault: Path,
    path: Path,
    ignore_patterns: list[str],
) -> bool:
    """Return True if `path` is a markdown file inside `vault` that does not
    match any of `ignore_patterns` (fnmatch against the vault-relative path).
    """
    vault = vault.resolve()
    try:
        rel = path.resolve().relative_to(vault)
    except ValueError:
        return False
    if path.suffix.lower() != ".md":
        return False
    rel_str = str(rel)
    for pat in ignore_patterns:
        if fnmatch.fnmatch(rel_str, pat):
            return False
        # Also match any path component (e.g. ".git/*" against "Notes/.git/x.md").
        for part in rel.parts:
            if fnmatch.fnmatch(part, pat.rstrip("/*")):
                return False
    return True
