"""Regression tests for supervisor XML-RPC transport auth host parsing."""

from pathlib import Path


def _method_block(content: str, method_name: str) -> str:
    marker = f"def {method_name}("
    start = content.find(marker)
    assert start != -1, f"Missing method: {method_name}"
    next_start = content.find("\n    def ", start + len(marker))
    if next_start == -1:
        return content[start:]
    return content[start:next_start]


def test_unix_transport_make_connection_uses_host_info_parsing() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "supervisor.py"
    ).read_text(encoding="utf-8")
    method = _method_block(source, "make_connection")

    assert "self.get_host_info(host)" in method
    assert "UnixStreamHTTPConnection(chost, self.socket_path)" in method
