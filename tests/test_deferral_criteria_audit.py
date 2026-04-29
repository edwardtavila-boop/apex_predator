from __future__ import annotations

from typing import TYPE_CHECKING

from eta_engine.scripts import _audit_deferral_criteria

if TYPE_CHECKING:
    from pathlib import Path


def test_deferral_audit_skips_frozen_bump_scripts(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "_bump_roadmap_v0_1_59.py").write_text(
        'NOTE = "enforcement deferred to v0.2.x"\n',
        encoding="utf-8",
    )

    assert _audit_deferral_criteria.scan(tmp_path) == []


def test_deferral_audit_still_scans_active_source(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    active = scripts / "active_runtime.py"
    active.write_text(
        'NOTE = "enforcement deferred to v0.2.x"\n',
        encoding="utf-8",
    )

    hits = _audit_deferral_criteria.scan(tmp_path)

    assert len(hits) == 1
    assert hits[0].file == "scripts/active_runtime.py"
    assert hits[0].has_criterion is False
