"""Ldap3Gateway against a fake ldap3 connection: paging, errors, reconnect, read-only, encryption rules."""
import socket

import pytest

from adtoolkit.core import errors as E
from adtoolkit.ldap.gateway import ModOp, Scope, SearchStats
from adtoolkit.ldap.ldap3_gateway import PAGED_RESULTS_OID, Ldap3Gateway
from adtoolkit.models.connection import AuthMethod, ConnectionProfile, SecurityMode

ROOT_DSE = {"defaultNamingContext": [b"DC=corp,DC=local"], "configurationNamingContext": [b"CN=Configuration,DC=corp,DC=local"],
            "dnsHostName": [b"dc01.corp.local"], "supportedControl": [PAGED_RESULTS_OID.encode()],
            "domainFunctionality": [b"7"]}


class _Ext:
    def __init__(self, conn):
        self.standard = self
        self.microsoft = self
        self.conn = conn

    def who_am_i(self):
        return "u:CORP\\admin"

    def modify_password(self, dn, pwd):
        self.conn.passwords.append(dn)
        self.conn.result = {"result": self.conn.password_result, "message": self.conn.password_message}
        return self.conn.password_result == 0


class FakeConn:
    def __init__(self, entries=0, page_limit=None, bind_result=None):
        self.entries = [f"CN=u{i},DC=corp,DC=local" for i in range(entries)]
        self.result = {}
        self.response = []
        self.bound = False
        self.closed = True
        self.searches = []
        self.modifies = []
        self.passwords = []
        self.fail_search = []        # exceptions raised by next search calls
        self.search_result = None    # forced result dict
        self.bind_result = bind_result
        self.password_result = 0
        self.password_message = ""
        self.extend = _Ext(self)

    def open(self):
        self.closed = False
        return True

    def start_tls(self):
        return True

    def bind(self):
        if self.bind_result:
            self.result = self.bind_result
            return False
        self.bound = True
        self.result = {"result": 0}
        return True

    def unbind(self):
        self.closed, self.bound = True, False

    def search(self, search_base, search_filter, search_scope, attributes, size_limit=0, time_limit=0, controls=None,
               paged_size=None, paged_cookie=None):
        self.searches.append(dict(base=search_base, filter=search_filter, scope=search_scope, paged_size=paged_size,
                                  cookie=paged_cookie, controls=controls))
        if self.fail_search:
            raise self.fail_search.pop(0)
        if self.search_result:
            self.result, self.response = dict(self.search_result), []
            return False
        if search_base == "":
            self.response = [{"type": "searchResEntry", "dn": "", "raw_attributes": ROOT_DSE}]
            self.result = {"result": 0, "controls": {}}
            return True
        start = int(paged_cookie or 0)
        items = self.entries
        if size_limit and len(items) > size_limit:
            page = items[:size_limit]
            self.response = [{"type": "searchResEntry", "dn": d, "raw_attributes": {"cn": [d[3:].split(",")[0].encode()]}} for d in page]
            self.result = {"result": 4, "description": "sizeLimitExceeded"}
            return True
        size = paged_size or len(items) or 1
        page = items[start:start + size]
        nxt = start + size
        cookie = str(nxt).encode() if paged_size and nxt < len(items) else b""
        self.response = [{"type": "searchResEntry", "dn": d, "raw_attributes": {"cn": [d[3:].split(",")[0].encode()]}} for d in page]
        self.response.append({"type": "searchResRef", "uri": ["ldap://other/"]})
        self.result = {"result": 0, "controls": {PAGED_RESULTS_OID: {"value": {"cookie": cookie}}}}
        return True

    def modify(self, dn, changes):
        self.modifies.append((dn, changes))
        self.result = {"result": 0}
        return True

    def add(self, dn, oc, attrs):
        self.result = {"result": 0}
        return True

    def delete(self, dn):
        self.result = {"result": 0}
        return True

    def modify_dn(self, dn, rdn, new_superior=None):
        self.result = {"result": 0}
        return True


def profile(**kw):
    p = ConnectionProfile(server="dc01.corp.local", port=636, security=SecurityMode.LDAPS, auth=AuthMethod.SIMPLE,
                          username="admin@corp.local", read_only=False, reconnect_attempts=2)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def gateway(conn, **kw):
    gw = Ldap3Gateway(profile(**kw), "S3cret!Pass", connection_factory=lambda g: conn)
    gw.connect()
    return gw


def test_connect_discovers_directory():
    conn = FakeConn()
    gw = gateway(conn)
    assert gw.info.domain_dns == "corp.local"
    assert gw.info.dc_host == "dc01.corp.local"
    assert gw.info.base_dn == "DC=corp,DC=local"
    assert gw.info.bound_identity == "u:CORP\\admin"
    assert gw.encrypted


def test_paged_search_follows_cookies():
    conn = FakeConn(entries=1203)
    gw = gateway(conn)
    gw.default_page_size = 500
    stats = SearchStats()
    items = list(gw.search("DC=corp,DC=local", "(objectClass=user)", ["cn"], stats=stats))
    assert len(items) == 1203
    assert stats.pages == 3
    assert stats.referrals == 3
    paged = [s for s in conn.searches if s["base"] == "DC=corp,DC=local" and s["paged_size"]]
    assert [s["cookie"] for s in paged[-3:]] == [None, b"500", b"1000"]


def test_base_search_is_not_paged():
    conn = FakeConn(entries=2)
    gw = gateway(conn)
    list(gw.search("CN=u1,DC=corp,DC=local", "(objectClass=*)", ["cn"], Scope.BASE))
    assert conn.searches[-1]["paged_size"] is None


def test_size_limit_marks_truncated():
    conn = FakeConn(entries=10)
    gw = gateway(conn)
    stats = SearchStats()
    items = list(gw.search("DC=corp,DC=local", "(cn=*)", ["cn"], size_limit=3, page_size=0, stats=stats))
    assert len(items) == 3 and stats.truncated


def test_search_filter_string_is_validated_before_sending():
    conn = FakeConn()
    gw = gateway(conn)
    with pytest.raises(ValueError):
        list(gw.search("DC=corp,DC=local", "(cn=a", ["cn"]))


@pytest.mark.parametrize("result,exc", [
    ({"result": 50, "message": "00000005: SecErr: DSID-03152870, problem 4003 (INSUFF_ACCESS_RIGHTS)"}, E.PermissionDeniedError),
    ({"result": 32, "message": "0000208D: NameErr: problem 2001 (NO_OBJECT)"}, E.ObjectNotFoundError),
    ({"result": 11, "description": "adminLimitExceeded"}, E.ToolkitError),
    ({"result": 3, "description": "timeLimitExceeded"}, E.LdapTimeoutError),
])
def test_search_errors_mapped(result, exc):
    conn = FakeConn()
    gw = gateway(conn)
    conn.search_result = result
    with pytest.raises(exc):
        list(gw.search("DC=corp,DC=local", "(cn=*)", ["cn"]))


@pytest.mark.parametrize("sub,text", [("52e", "Неверное имя пользователя или пароль"), ("775", "заблокирована"),
                                      ("532", "пароля истёк"), ("533", "отключена"), ("701", "учётной записи истёк")])
def test_bind_errors_mapped(sub, text):
    conn = FakeConn(bind_result={"result": 49, "message": f"80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data {sub}, v4563"})
    gw = Ldap3Gateway(profile(), "WrongPassword", connection_factory=lambda g: conn)
    with pytest.raises(E.AuthenticationError) as e:
        gw.connect()
    assert text in e.value.message
    assert "WrongPassword" not in e.value.full_text()


def test_stronger_auth_required():
    conn = FakeConn(bind_result={"result": 8, "message": "00002028: LdapErr: DSID-0C090259, comment: The server requires binds to turn on integrity checking"})
    gw = Ldap3Gateway(profile(), "x", connection_factory=lambda g: conn)
    with pytest.raises(E.InsecureConnectionError):
        gw.connect()


def test_password_never_sent_over_plain_ldap():
    gw = Ldap3Gateway(profile(security=SecurityMode.PLAIN, port=389), "x", connection_factory=lambda g: FakeConn())
    with pytest.raises(E.InsecureConnectionError):
        gw.connect()


def test_plain_kerberos_requires_explicit_opt_in():
    p = dict(security=SecurityMode.PLAIN, port=389, auth=AuthMethod.KERBEROS, username="")
    with pytest.raises(E.InsecureConnectionError):
        Ldap3Gateway(profile(**p), None, connection_factory=lambda g: FakeConn()).connect()
    gw = Ldap3Gateway(profile(allow_unencrypted_kerberos=True, **p), None, connection_factory=lambda g: FakeConn())
    info = gw.connect()
    assert not info.encrypted and info.warnings
    with pytest.raises(E.InsecureConnectionError):
        gw.set_password("CN=u1,DC=corp,DC=local", "Passw0rd!Passw0rd")


def test_connection_errors_mapped():
    class Boom(FakeConn):
        def open(self):
            raise socket.timeout("timed out")
    with pytest.raises(E.LdapTimeoutError):
        Ldap3Gateway(profile(), "x", connection_factory=lambda g: Boom()).connect()

    class Cert(FakeConn):
        def open(self):
            raise OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")
    with pytest.raises(E.CertificateError):
        Ldap3Gateway(profile(), "x", connection_factory=lambda g: Cert()).connect()


def test_read_is_retried_after_reconnect(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = FakeConn(entries=3)
    gw = gateway(conn)
    LDAPSocketReceiveError = type("LDAPSocketReceiveError", (Exception,), {})
    conn.fail_search.append(LDAPSocketReceiveError("connection reset"))
    events = []
    gw.add_listener(lambda s, m: events.append(s))
    items = list(gw.search("DC=corp,DC=local", "(cn=*)", ["cn"]))
    assert len(items) == 3
    assert "reconnecting" in events and events[-1] == "connected"


def test_write_is_not_retried_after_connection_loss(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = FakeConn()
    gw = gateway(conn)
    LDAPSocketSendError = type("LDAPSocketSendError", (Exception,), {})

    def broken(dn, changes):
        raise LDAPSocketSendError("broken pipe")
    conn.modify = broken
    with pytest.raises(E.ConnectionLostError) as e:
        gw.modify("CN=u1,DC=corp,DC=local", {"description": [(ModOp.REPLACE, ["x"])]})
    assert "результат неизвестен" in e.value.message


def test_read_only_blocks_writes_before_network():
    conn = FakeConn()
    gw = gateway(conn, read_only=True)
    with pytest.raises(E.ReadOnlyModeError):
        gw.modify("CN=u1,DC=corp,DC=local", {"description": [(ModOp.REPLACE, ["x"])]})
    with pytest.raises(E.ReadOnlyModeError):
        gw.set_password("CN=u1,DC=corp,DC=local", "x")
    assert conn.modifies == [] and conn.passwords == []


def test_no_such_attribute_maps_to_conflict():
    conn = FakeConn()
    gw = gateway(conn)
    conn.modify = lambda dn, ch: (setattr(conn, "result", {"result": 16, "message": "00002080: AtrErr: DSID-03152B1A, problem 1001 (NO_ATTRIBUTE_OR_VAL)"}), False)[1]
    with pytest.raises(E.ConflictError):
        gw.modify("CN=u1,DC=corp,DC=local", {"title": [(ModOp.DELETE, ["old"]), (ModOp.ADD, ["new"])]})


def test_unicodepwd_cannot_be_written_via_modify():
    gw = gateway(FakeConn())
    with pytest.raises(E.ValidationError):
        gw.modify("CN=u1,DC=corp,DC=local", {"unicodePwd": [(ModOp.REPLACE, [b"x"])]})


def test_password_policy_error_mapped_and_masked():
    conn = FakeConn()
    gw = gateway(conn)
    conn.password_result = 19
    conn.password_message = "0000052D: Constraint violation - check_password_restrictions: the password does not meet the complexity criteria!"
    with pytest.raises(E.PasswordPolicyError) as e:
        gw.set_password("CN=u1,DC=corp,DC=local", "MyNewPa55!")
    assert "MyNewPa55!" not in e.value.full_text()
