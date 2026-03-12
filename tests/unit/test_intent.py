"""Tests for intent detection engine."""

import pytest

from kage.core.intent import (
    Intent,
    IntentResult,
    classify_intent,
    needs_ai_classification,
)


class TestIntentClassification:
    """Test intent classification for various user inputs."""

    # --- Security intent ---

    def test_security_tool_direct(self):
        result = classify_intent("nmap -sV 192.168.1.1")
        assert result.intent == Intent.SECURITY
        assert result.confidence >= 0.9
        assert "nmap" in result.matched_keywords

    def test_security_tool_run_prefix(self):
        result = classify_intent("run sqlmap -u http://target.com")
        assert result.intent == Intent.SECURITY
        assert "sqlmap" in result.matched_keywords

    def test_security_keywords(self):
        result = classify_intent("scan example.com for vulnerabilities")
        assert result.intent == Intent.SECURITY

    def test_security_exploit_request(self):
        result = classify_intent("exploit the SQL injection on target")
        assert result.intent == Intent.SECURITY

    def test_nikto_scan(self):
        result = classify_intent("nikto -h http://192.168.1.1")
        assert result.intent == Intent.SECURITY
        assert result.confidence >= 0.9

    def test_hydra_brute(self):
        result = classify_intent("hydra -l admin -P wordlist.txt ssh://10.0.0.1")
        assert result.intent == Intent.SECURITY

    def test_gobuster_dir(self):
        result = classify_intent("gobuster dir -u http://target.com -w wordlist.txt")
        assert result.intent == Intent.SECURITY

    # --- Development intent ---

    def test_dev_tool_python(self):
        result = classify_intent("python app.py")
        assert result.intent == Intent.DEVELOPMENT
        assert result.confidence >= 0.85

    def test_dev_tool_git(self):
        result = classify_intent("git commit -m 'fix bug'")
        assert result.intent == Intent.DEVELOPMENT

    def test_dev_tool_pip(self):
        result = classify_intent("pip install flask")
        assert result.intent == Intent.DEVELOPMENT

    def test_dev_tool_npm(self):
        result = classify_intent("npm run build")
        assert result.intent == Intent.DEVELOPMENT

    def test_dev_keywords(self):
        result = classify_intent("create a flask api with endpoints for users")
        assert result.intent == Intent.DEVELOPMENT

    # --- System intent ---

    def test_system_tool_apt(self):
        result = classify_intent("apt install curl")
        assert result.intent == Intent.SYSTEM

    def test_system_tool_ls(self):
        result = classify_intent("ls -la /etc")
        assert result.intent == Intent.SYSTEM

    def test_system_tool_systemctl(self):
        result = classify_intent("systemctl restart nginx")
        assert result.intent == Intent.SYSTEM

    # --- Chat intent ---

    def test_chat_question_what(self):
        result = classify_intent("what is SQL injection?")
        assert result.intent == Intent.CHAT
        assert result.confidence >= 0.8

    def test_chat_question_how(self):
        result = classify_intent("how does DNS work?")
        assert result.intent == Intent.CHAT

    def test_chat_explain(self):
        result = classify_intent("explain buffer overflow attacks")
        assert result.intent == Intent.CHAT

    def test_chat_question_mark(self):
        result = classify_intent("is this a vulnerability?")
        assert result.intent == Intent.CHAT

    def test_chat_describe(self):
        result = classify_intent("describe the OWASP top 10")
        assert result.intent == Intent.CHAT

    def test_chat_empty_input(self):
        result = classify_intent("")
        assert result.intent == Intent.CHAT
        assert result.confidence == 1.0

    # --- Ambiguous cases ---

    def test_ambiguous_low_confidence(self):
        result = classify_intent("hello")
        assert result.intent == Intent.CHAT
        assert result.confidence < 0.6

    def test_needs_ai_classification_ambiguous(self):
        result = classify_intent("hello")
        assert needs_ai_classification(result) is True

    def test_no_ai_needed_for_clear(self):
        result = classify_intent("nmap 10.0.0.1")
        assert needs_ai_classification(result) is False

    def test_security_with_target_pattern(self):
        result = classify_intent("scan 192.168.1.0/24 for open ports")
        assert result.intent == Intent.SECURITY


class TestIntentResult:
    """Test IntentResult model."""

    def test_model_validation(self):
        result = IntentResult(
            intent=Intent.SECURITY,
            confidence=0.95,
            matched_keywords=["nmap"],
            reasoning="Security tool",
        )
        assert result.intent == Intent.SECURITY
        assert result.confidence == 0.95

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            IntentResult(intent=Intent.CHAT, confidence=1.5)

        with pytest.raises(Exception):
            IntentResult(intent=Intent.CHAT, confidence=-0.1)
