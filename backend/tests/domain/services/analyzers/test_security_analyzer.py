"""Tests for security analyzer scanning logic."""

from app.domain.services.analyzers.security_analyzer import SecurityAnalyzer


class TestSecurityAnalyzerScan:
    """Test security scanning logic."""

    def test_detect_sql_injection_pattern(self) -> None:
        """Should detect SQL injection patterns."""
        analyzer = SecurityAnalyzer()
        code = """
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
"""
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "SQL_INJECTION" for v in vulns)

    def test_detect_sql_injection_percent_format(self) -> None:
        """Should detect SQL injection with % formatting."""
        analyzer = SecurityAnalyzer()
        code = """
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = %s" % user_id
    cursor.execute(query)
"""
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "SQL_INJECTION" for v in vulns)

    def test_detect_command_injection_os_system(self) -> None:
        """Should detect command injection with os.system."""
        analyzer = SecurityAnalyzer()
        code = """
import os
def run_cmd(user_input):
    os.system(f"echo {user_input}")
"""
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "COMMAND_INJECTION" for v in vulns)

    def test_detect_command_injection_subprocess_shell(self) -> None:
        """Should detect command injection with subprocess shell=True."""
        analyzer = SecurityAnalyzer()
        code = """
import subprocess
def run_cmd(user_input):
    subprocess.run(f"echo {user_input}", shell=True)
"""
        vulns = analyzer.scan_code(code, "test.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "COMMAND_INJECTION" for v in vulns)

    def test_detect_hardcoded_api_key(self) -> None:
        """Should detect hardcoded API keys."""
        analyzer = SecurityAnalyzer()
        code = """
API_KEY = "sk-1234567890abcdef"
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "HARDCODED_SECRET" for v in vulns)

    def test_detect_hardcoded_password(self) -> None:
        """Should detect hardcoded passwords."""
        analyzer = SecurityAnalyzer()
        code = """
PASSWORD = "supersecret123"
DB_PASSWORD = "admin123"
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "HARDCODED_SECRET" for v in vulns)

    def test_detect_hardcoded_secret_token(self) -> None:
        """Should detect hardcoded secret tokens."""
        analyzer = SecurityAnalyzer()
        code = """
SECRET_KEY = "mysupersecretkey12345"
AUTH_TOKEN = "token_abcdef123456"
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        assert any(v.vulnerability_type == "HARDCODED_SECRET" for v in vulns)

    def test_safe_code_no_vulnerabilities(self) -> None:
        """Safe code should return no vulnerabilities."""
        analyzer = SecurityAnalyzer()
        code = """
def add(a: int, b: int) -> int:
    return a + b
"""
        vulns = analyzer.scan_code(code, "math.py", "python")
        assert len(vulns) == 0

    def test_safe_parameterized_query(self) -> None:
        """Parameterized queries should not trigger SQL injection."""
        analyzer = SecurityAnalyzer()
        code = """
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
"""
        vulns = analyzer.scan_code(code, "test.py", "python")
        # Parameterized queries are safe
        sql_vulns = [v for v in vulns if v.vulnerability_type == "SQL_INJECTION"]
        assert len(sql_vulns) == 0

    def test_env_variable_not_hardcoded(self) -> None:
        """Environment variable lookups should not be flagged."""
        analyzer = SecurityAnalyzer()
        code = """
import os
API_KEY = os.environ.get("API_KEY")
PASSWORD = os.getenv("DB_PASSWORD")
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        secret_vulns = [v for v in vulns if v.vulnerability_type == "HARDCODED_SECRET"]
        assert len(secret_vulns) == 0

    def test_vulnerability_has_line_number(self) -> None:
        """Vulnerabilities should include accurate line numbers."""
        analyzer = SecurityAnalyzer()
        code = """line 1
line 2
API_KEY = "sk-secret123"
line 4
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        # The API_KEY is on line 3
        assert any(v.line_number == 3 for v in vulns)

    def test_vulnerability_has_code_snippet(self) -> None:
        """Vulnerabilities should include the offending code snippet."""
        analyzer = SecurityAnalyzer()
        code = """
API_KEY = "sk-secret123"
"""
        vulns = analyzer.scan_code(code, "config.py", "python")
        assert len(vulns) >= 1
        assert any("API_KEY" in v.code_snippet for v in vulns)

    def test_unsupported_language_returns_empty(self) -> None:
        """Unsupported languages should return empty list (for now)."""
        analyzer = SecurityAnalyzer()
        code = """
const apiKey = "sk-secret123";
"""
        vulns = analyzer.scan_code(code, "config.js", "javascript")
        # JavaScript not yet supported
        assert len(vulns) == 0

    def test_multiple_vulnerabilities_detected(self) -> None:
        """Should detect multiple vulnerabilities in same code."""
        analyzer = SecurityAnalyzer()
        code = """
import os
API_KEY = "sk-1234567890"
def run(cmd):
    os.system(f"echo {cmd}")
def query(id):
    cursor.execute(f"SELECT * FROM t WHERE id = {id}")
"""
        vulns = analyzer.scan_code(code, "bad.py", "python")
        assert len(vulns) >= 3
        types = {v.vulnerability_type for v in vulns}
        assert "HARDCODED_SECRET" in types
        assert "COMMAND_INJECTION" in types
        assert "SQL_INJECTION" in types


class TestSecurityAnalyzerSeverity:
    """Test vulnerability severity assignment."""

    def test_sql_injection_is_high_severity(self) -> None:
        """SQL injection should be HIGH severity."""
        analyzer = SecurityAnalyzer()
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        vulns = analyzer.scan_code(code, "test.py", "python")
        sql_vulns = [v for v in vulns if v.vulnerability_type == "SQL_INJECTION"]
        assert len(sql_vulns) >= 1
        assert all(v.severity == "HIGH" for v in sql_vulns)

    def test_command_injection_is_critical_severity(self) -> None:
        """Command injection should be CRITICAL severity."""
        analyzer = SecurityAnalyzer()
        code = 'os.system(f"rm {path}")'
        vulns = analyzer.scan_code(code, "test.py", "python")
        cmd_vulns = [v for v in vulns if v.vulnerability_type == "COMMAND_INJECTION"]
        assert len(cmd_vulns) >= 1
        assert all(v.severity == "CRITICAL" for v in cmd_vulns)

    def test_hardcoded_secret_is_medium_severity(self) -> None:
        """Hardcoded secrets should be MEDIUM severity."""
        analyzer = SecurityAnalyzer()
        code = 'PASSWORD = "secret123"'
        vulns = analyzer.scan_code(code, "test.py", "python")
        secret_vulns = [v for v in vulns if v.vulnerability_type == "HARDCODED_SECRET"]
        assert len(secret_vulns) >= 1
        assert all(v.severity == "MEDIUM" for v in secret_vulns)


class TestSecurityAnalyzerAnalyzeMethod:
    """Test the existing analyze() method still works."""

    def test_analyze_method_returns_vulnerabilities(self) -> None:
        """The analyze() method should also detect vulnerabilities."""
        analyzer = SecurityAnalyzer()
        code = 'API_KEY = "sk-secret123"'
        vulns = analyzer.analyze(code, "test.py", "python")
        # analyze() should call scan_code internally
        assert len(vulns) >= 1
