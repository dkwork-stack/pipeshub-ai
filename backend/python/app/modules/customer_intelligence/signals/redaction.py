"""PII redaction applied before text leaves for the LLM and before excerpts are stored.

Data minimisation (GDPR Art. 5(1)(c), Art. 25): asks and pain points do not
need anyone's email address or phone number to be useful. Company names are
business data and are kept. ``IPiiRedactor`` is the seam for a stronger
engine (Presidio, a cloud DLP API) when a customer contract requires one.
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod


class IPiiRedactor(ABC):
    @abstractmethod
    def redact(self, text: str) -> str: ...


class NoopRedactor(IPiiRedactor):
    def redact(self, text: str) -> str:
        return text


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class RegexPiiRedactor(IPiiRedactor):
    """Deterministic, dependency-free baseline. Order matters: specific before generic."""

    _EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
    _IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")
    _CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
    _US_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    _PHONE = re.compile(r"(?<![\w/])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]\d{2,4}){1,4}(?![\w/])")
    _IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def redact(self, text: str) -> str:
        if not text:
            return text
        text = self._EMAIL.sub("[email]", text)
        text = self._IBAN.sub("[iban]", text)
        text = self._CARD.sub(self._card, text)
        text = self._US_SSN.sub("[id-number]", text)
        text = self._IPV4.sub("[ip]", text)
        return self._PHONE.sub(self._phone, text)

    @staticmethod
    def _card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return "[card]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)

    @staticmethod
    def _phone(match: re.Match[str]) -> str:
        value = match.group(0)
        digits = re.sub(r"\D", "", value)
        # Dates (2026-10-01) and long reference numbers are not phone numbers (E.164 caps at 15 digits).
        if not 8 <= len(digits) <= 15 or re.fullmatch(r"\d{4}[-/.]\d{2}[-/.]\d{2}", value.strip()):
            return value
        return "[phone]"


def create_redactor() -> IPiiRedactor:
    enabled = os.getenv("INTELLIGENCE_PII_REDACTION", "true").strip().lower() not in {"0", "false", "no", "off"}
    return RegexPiiRedactor() if enabled else NoopRedactor()
