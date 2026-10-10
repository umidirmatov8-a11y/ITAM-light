"""Ldap3Gateway with a real ``ldap3.Connection`` (MOCK_SYNC strategy): verifies the actual ldap3 API usage —
paged results, raw attribute decoding, modify with delete+add (optimistic concurrency), modify_dn, error results.

ldap3's mock strategy cannot answer a RootDSE query (empty base), so only that single call is emulated.
"""
import pytest
from ldap3 import MOCK_SYNC, Connection, Server

from adtoolkit.core import errors as E
from adtoolkit.ldap.gateway import ModOp, Scope, SearchStats
from adtoolkit.ldap.ldap3_gateway import Ldap3Gateway
from adtoolkit.models.connection import ConnectionProfile


class RootDseConnection(Connection):
    def search(self, search_base, search_filter, *args, **kwargs):
        if search_base == "":
            self.result = {"result": 0, "description": "success", "controls": {}}
            self.response = [{"type": "searchResEntry", "dn": "", "raw_attributes": {
                "defaultNamingContext": [b"DC=corp,DC=local"], "dnsHostName": [b"dc01.corp.local"],
                "supportedControl": [b"1.2.840.113556.1.4.319"]}, "attributes": {}}]
            return True
        return super().search(search_base, search_filter, *args, **kwargs)


def factory(_gw):
    c = RootDseConnection(Server("dc01.corp.local"), user="CN=admin,DC=corp,DC=local", password="Secret1!",
                          client_strategy=MOCK_SYNC, raise_exceptions=False)
    c.strategy.add_entry("CN=admin,DC=corp,DC=local", {"userPassword": "Secret1!", "objectClass": ["top", "person", "user"],
                                                        "sAMAccountName": "admin"})
    c.strategy.add_entry("DC=corp,DC=local", {"objectClass": ["top", "domain"], "dc": "corp"})
    c.strategy.add_entry("OU=Archive,DC=corp,DC=local", {"objectClass": ["top", "organizationalUnit"], "ou": "Archive"})
    for i in range(1205):
        c.strategy.add_entry(f"CN=u{i},DC=corp,DC=local", {"objectClass": ["top", "person", "user"], "cn": f"u{i}",
                                                            "userAccountControl": "512", "sAMAccountName": f"u{i}"})
    return c


@pytest.fixture
def gw():
    p = ConnectionProfile(server="dc01.corp.local", username="CN=admin,DC=corp,DC=local", read_only=False, page_size=500)
    g = Ldap3Gateway(p, "Secret1!", connection_factory=factory)
    g.connect()
    return g


def test_connect_and_paged_search(gw):
    assert gw.info.base_dn == "DC=corp,DC=local" and gw.info.dc_host == "dc01.corp.local"
    stats = SearchStats()
    items = list(gw.search("DC=corp,DC=local", "(&(objectClass=user)(sAMAccountName=u*))", ["cn", "userAccountControl"],
                           stats=stats))
    assert len(items) == 1205 and stats.pages == 3
    assert items[0].int("userAccountControl") == 512


def test_modify_with_optimistic_concurrency(gw):
    dn = "CN=u1,DC=corp,DC=local"
    gw.modify(dn, {"userAccountControl": [(ModOp.DELETE, ["512"]), (ModOp.ADD, ["514"])]})
    assert gw.get(dn, ["userAccountControl"]).int("userAccountControl") == 514
    # the old value is gone: the change is rejected instead of silently overwriting (AD answers noSuchAttribute,
    # mapped to ConflictError — see test_ldap3_gateway; ldap3's mock answers operationsError)
    with pytest.raises(E.ToolkitError):
        gw.modify(dn, {"userAccountControl": [(ModOp.DELETE, ["512"]), (ModOp.ADD, ["514"])]})
    assert gw.get(dn, ["userAccountControl"]).int("userAccountControl") == 514


def test_move_and_errors(gw):
    new_dn = gw.move("CN=u2,DC=corp,DC=local", "OU=Archive,DC=corp,DC=local")
    assert new_dn == "CN=u2,OU=Archive,DC=corp,DC=local"
    assert gw.get(new_dn, ["cn"]) is not None
    assert gw.get("CN=missing,DC=corp,DC=local", ["cn"]) is None
    assert len(list(gw.search("OU=Archive,DC=corp,DC=local", "(objectClass=user)", ["cn"], Scope.ONELEVEL))) == 1
