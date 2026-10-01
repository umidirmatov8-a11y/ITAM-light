"""Behavioural event categories used for correlation, explanations and recommendations."""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    AUTH_FAILURE = "auth_failure"
    BRUTE_FORCE = "brute_force"
    AUTH_SUCCESS = "auth_success"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    ACCOUNT_CHANGE = "account_change"
    EXECUTION = "execution"
    PROCESS_ACTIVITY = "process_activity"
    CREDENTIAL_ACCESS = "credential_access"
    PERSISTENCE = "persistence"
    DEFENSE_EVASION = "defense_evasion"
    LATERAL_MOVEMENT = "lateral_movement"
    NETWORK_C2 = "network_c2"
    NETWORK = "network"
    SCAN = "scan"
    WEB_ATTACK = "web_attack"
    MALWARE = "malware"
    IMPACT = "impact"
    FIM = "fim"
    VULNERABILITY = "vulnerability"
    POLICY = "policy"
    SYSTEM = "system"
    OTHER = "other"

    @property
    def label(self) -> str:
        from app.i18n import tr
        return tr(CATEGORY_LABELS[self])

    @classmethod
    def parse(cls, value: str | None) -> "Category":
        try:
            return cls(value) if value else cls.OTHER
        except ValueError:
            return cls.OTHER


CATEGORY_LABELS: dict[Category, str] = {
    Category.AUTH_FAILURE: "Authentication failure",
    Category.BRUTE_FORCE: "Brute-force / password guessing",
    Category.AUTH_SUCCESS: "Successful authentication",
    Category.PRIVILEGE_ESCALATION: "Privilege escalation / elevated execution",
    Category.ACCOUNT_CHANGE: "Account or group change",
    Category.EXECUTION: "Suspicious command execution",
    Category.PROCESS_ACTIVITY: "Process activity",
    Category.CREDENTIAL_ACCESS: "Credential access",
    Category.PERSISTENCE: "Persistence mechanism",
    Category.DEFENSE_EVASION: "Defense evasion",
    Category.LATERAL_MOVEMENT: "Lateral movement",
    Category.NETWORK_C2: "Suspicious outbound connection",
    Category.NETWORK: "Network activity",
    Category.SCAN: "Scanning / reconnaissance",
    Category.WEB_ATTACK: "Web attack",
    Category.MALWARE: "Malware detection",
    Category.IMPACT: "Destructive / impact activity",
    Category.FIM: "File integrity change",
    Category.VULNERABILITY: "Vulnerability",
    Category.POLICY: "Configuration / compliance",
    Category.SYSTEM: "Agent / system event",
    Category.OTHER: "Other",
}

AUTH_FAILURE_CATEGORIES = frozenset({Category.AUTH_FAILURE.value, Category.BRUTE_FORCE.value})
