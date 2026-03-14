"""Tests for security tool output parser."""

from kage.security.output_parser import (
    parse_gobuster_output,
    parse_nikto_output,
    parse_nmap_output,
    parse_sqlmap_output,
    parse_tool_output,
)


def test_parse_nmap_output_extracts_open_ports() -> None:
    output = """
PORT     STATE SERVICE VERSION
22/tcp   open  ssh     OpenSSH 8.9
80/tcp   open  http    nginx 1.18.0
443/tcp  closed https
"""
    parsed = parse_nmap_output(output)
    assert parsed["open_ports"] == [22, 80]
    assert parsed["services"] == ["ssh", "http"]
    assert parsed["ports"][0]["port"] == 22


def test_parse_gobuster_output_extracts_directories() -> None:
    output = """
/admin (Status: 301) [Size: 0]
/login (Status: 200) [Size: 1234]
Found: /backup
"""
    parsed = parse_gobuster_output(output)
    assert parsed["directories"] == ["/admin", "/login", "/backup"]


def test_parse_nikto_output_extracts_findings() -> None:
    output = """
- Nikto v2.5.0
+ Target Host: example.com
+ Target Port: 80
+ /admin/: Admin portal found
+ /phpinfo.php: phpinfo exposed
"""
    parsed = parse_nikto_output(output)
    assert parsed["target"]["host"] == "example.com"
    assert parsed["target"]["port"] == 80
    assert parsed["vulnerabilities_detected"] is True
    assert "Admin portal found" in parsed["findings"][0]


def test_parse_sqlmap_output_extracts_vulnerability_data() -> None:
    output = """
[INFO] parameter 'id' appears to be injectable
[INFO] back-end DBMS: MySQL
Parameter: id (GET)
[*] information_schema
[*] appdb
| users |
| orders |
"""
    parsed = parse_sqlmap_output(output)
    assert parsed["vulnerable"] is True
    assert parsed["dbms"] == "MySQL"
    assert "id" in parsed["parameters"]
    assert "appdb" in parsed["databases"]
    assert "users" in parsed["tables"]


def test_parse_tool_output_dispatch_and_unknown() -> None:
    known = parse_tool_output("nmap", "80/tcp open http")
    assert known["supported"] is True
    assert known["tool"] == "nmap"

    unknown = parse_tool_output("customtool", "anything")
    assert unknown["supported"] is False
    assert unknown["parsed"] is None
