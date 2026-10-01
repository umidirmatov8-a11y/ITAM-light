import json

from app.core.config import PrivacyConfig
from app.privacy.sanitizer import Sanitizer


def make(**kw):
    return Sanitizer(PrivacyConfig(internal_domains=["company.uz"], **kw), known_users=["j.doe", "ivanov"],
                     known_hosts=["web-01", "dc-01"])


def test_email_and_internal_ip():
    s = make()
    out = s.sanitize_text("ivanov@company.uz from 10.20.14.55")
    assert out == "[USER_EMAIL_001] from [INTERNAL_IP_001]"
    assert s.restore(out) == "ivanov@company.uz from 10.20.14.55"


def test_consistent_placeholders():
    s = make()
    a = s.sanitize_text("10.0.0.1 then 10.0.0.2 then 10.0.0.1")
    assert a == "[INTERNAL_IP_001] then [INTERNAL_IP_002] then [INTERNAL_IP_001]"


def test_external_ip_kept_by_default_and_maskable():
    assert "203.0.113.5" in make().sanitize_text("from 203.0.113.5")
    assert "[EXTERNAL_IP_001]" in make(mask_external_ips=True).sanitize_text("from 203.0.113.5")


def test_usernames_hosts_and_domains():
    s = make()
    out = s.sanitize_text(r"CORP\j.doe logged on web-01 (web-01.company.uz) C:\Users\ivanov\x.exe /home/j.doe/.ssh")
    for secret in ("j.doe", "ivanov", "web-01", "company.uz", "CORP"):
        assert secret not in out
    restored = s.restore(out)
    assert "j.doe" in restored and "ivanov" in restored


def test_log_patterns_reveal_no_unknown_usernames():
    s = make()
    out = s.sanitize_text("Failed password for invalid user sysadmin2 from 203.0.113.9 port 22; user=backupsvc")
    assert "sysadmin2" not in out and "backupsvc" not in out
    assert "203.0.113.9" in out


def test_system_accounts_not_masked():
    s = make()
    assert s.sanitize_text("Failed password for root from 10.0.0.1").startswith("Failed password for root")


def test_secrets_are_redacted_irreversibly():
    s = make()
    text = ("password=Sup3rS3cret! token: abcdef123456 Authorization: Bearer eyJhbGciOi.xyz Cookie: SID=abc; x=y "
            "api_key=AKIAABCDEFGHIJKLMNOP sk-proj-ABCDEFGHIJKLMNOPQRSTUV "
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
    out = s.sanitize_text(text)
    for secret in ("Sup3rS3cret!", "abcdef123456", "SID=abc", "AKIAABCDEFGHIJKLMNOP", "sk-proj-ABC",
                   "dozjgNryP4J3", "eyJhbGciOi.xyz"):
        assert secret not in out
    assert s.restore(out) == out  # secrets cannot be restored
    assert s.redacted_secrets == 1


def test_personal_data():
    s = make()
    out = s.sanitize_text("call +998 90 123 45 67 card 4111 1111 1111 1111 order 1234567890123")
    assert "+998" not in out and "4111" not in out
    assert "1234567890123" in out  # not a Luhn-valid card number


def test_structured_sanitization_by_key():
    s = make()
    out = s.sanitize({"user": "newuser1", "agent": "srv-unknown", "users": ["a.b"], "nested": {"source_ip": "10.1.1.1"},
                      "count": 5})
    dumped = json.dumps(out)
    assert "newuser1" not in dumped and "srv-unknown" not in dumped and "a.b" not in dumped
    assert "10.1.1.1" not in dumped and out["count"] == 5


def test_disabled_masking():
    s = Sanitizer(PrivacyConfig(mask_usernames=False, mask_internal_ips=False, mask_hostnames=False),
                  known_users=["bob"], known_hosts=["h1"])
    assert s.sanitize_text("bob on h1 from 10.0.0.1") == "bob on h1 from 10.0.0.1"
