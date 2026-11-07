"""Keep the P2 handoff and feature map aligned with the shipped facade."""

from pathlib import Path

from carbon_room import core

ROOT = Path(__file__).resolve().parents[1]


def test_p2_handoff_lists_implemented_facade_and_real_files():
    handoff = (ROOT / "docs/p2/HANDOFF.md").read_text(encoding="utf-8")
    for name in ("calculate", "check", "resolve", "summary", "draft_report", "trace", "publish"):
        assert callable(getattr(core, name))
        assert f"core.{name}(" in handoff
    assert "Not built yet" not in handoff
    assert "report.pdf" in handoff
    for path in (
        "carbon_room/calc/datacentre.py",
        "carbon_room/checks/run.py",
        "carbon_room/checks/resolve.py",
        "carbon_room/report/reporter.py",
        "carbon_room/report/publish.py",
        "carbon_room/report/pdf.py",
        "carbon_room/report/trace.py",
        "carbon_room/report/templates/report.md.j2",
        "carbon_room/report/templates/coverage.html.j2",
        "config/compliance_checks.yaml",
        "data/seed/EXPECTED.md",
    ):
        assert (ROOT / path).is_file(), path
