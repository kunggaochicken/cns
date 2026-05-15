from app.detectors.sidecar import write_conflict_sidecar


def test_writes_markdown_with_frontmatter(tmp_path):
    out = write_conflict_sidecar(
        vault_path=tmp_path,
        conflict_id="c_abcdef0123",
        summary="ship preview vs delay preview",
        new_thought_id="t_new",
        new_thought_content="we should ship preview now",
        candidate_thought_id="t_old",
        candidate_thought_content="agreed to delay preview a month",
        confidence=0.82,
    )
    assert out.exists()
    text = out.read_text()
    assert "conflict_id: c_abcdef0123" in text
    assert "status: open" in text
    assert "we should ship preview now" in text
    assert "agreed to delay preview a month" in text
    assert out.parent == tmp_path / "Brain" / "Reviews" / "conflicts"
