from pathlib import Path


def _section_block(content: str, section: str) -> str:
    marker = f"[{section}]"
    start = content.find(marker)
    assert start != -1, f"Missing section: {section}"
    # Find next section header after current start
    next_start = content.find("\n[", start + len(marker))
    if next_start == -1:
        return content[start:]
    return content[start:next_start]


def test_unix_http_server_requires_auth_credentials() -> None:
    cfg = Path(__file__).resolve().parents[1] / "supervisord.conf"
    text = cfg.read_text(encoding="utf-8")
    section = _section_block(text, "unix_http_server")

    assert "username=%(ENV_SUPERVISOR_RPC_USERNAME)s" in section
    assert "password=%(ENV_SUPERVISOR_RPC_PASSWORD)s" in section


def test_supervisorctl_uses_matching_auth_credentials() -> None:
    cfg = Path(__file__).resolve().parents[1] / "supervisord.conf"
    text = cfg.read_text(encoding="utf-8")
    section = _section_block(text, "supervisorctl")

    assert "username=%(ENV_SUPERVISOR_RPC_USERNAME)s" in section
    assert "password=%(ENV_SUPERVISOR_RPC_PASSWORD)s" in section


def test_x11vnc_uses_launcher_with_nonc() -> None:
    """Inflated RFB (e.g. 1280×12288) breaks noVNC scaling unless ncache is off."""
    root = Path(__file__).resolve().parents[1]
    cfg = root / "supervisord.conf"
    section = _section_block(cfg.read_text(encoding="utf-8"), "program:x11vnc")
    assert "run_x11vnc.sh" in section
    script = root / "scripts" / "run_x11vnc.sh"
    assert script.is_file()
    assert "-nonc" in script.read_text(encoding="utf-8")
