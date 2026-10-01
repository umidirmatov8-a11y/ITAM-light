"""Plain-language explanations that keep *facts* separate from *analysis*.

``evidence`` contains only observations taken from the logs.  ``what_happened`` describes
the observed events, ``why_it_matters`` / ``possible_attack`` contain analytical
interpretation, worded cautiously ("possible", "likely", "suspicious") unless confirmed by
a malicious indicator.  The analyzer never claims a system "has been hacked".

Texts are produced in the active language (:mod:`app.i18n`); ``assessment`` stays an English
key that is translated for display.
"""

from __future__ import annotations

from app.i18n import n, num, tr
from app.models.analysis import AlertGroup
from app.models.categories import Category
from app.utils.text import truncate_list
from app.utils.timeutil import fmt_duration, fmt_ts

C = Category

ASSESSMENTS = (
    "Confirmed malicious indicator",
    "Potential compromise",
    "Possible attack chain",
    "Likely brute-force activity",
    "Possible attack",
    "Suspicious activity",
    "Likely benign / possible false positive",
    "Informational event",
    "Insufficient evidence",
)


def _src(group: AlertGroup) -> str:
    if not group.src_ip:
        return tr("an unknown source")
    if group.src_external:
        return tr("external IP {ip}", ip=group.src_ip)
    return tr("internal IP {ip}", ip=group.src_ip)


def _host(group: AlertGroup) -> str:
    return group.agent_name or tr("an unidentified host")


def _period(group: AlertGroup) -> str:
    if group.first_ts is None:
        return ""
    if group.count == 1 or group.last_ts == group.first_ts:
        return tr(" at {time}", time=fmt_ts(group.first_ts))
    return tr(" between {start} and {end} ({duration})", start=fmt_ts(group.first_ts), end=fmt_ts(group.last_ts),
              duration=fmt_duration((group.last_ts or 0) - group.first_ts))


class Explainer:
    def __init__(self, rule_kb=None, bruteforce_threshold: int = 5):
        self.rule_kb = rule_kb
        self.threshold = bruteforce_threshold

    def explain(self, group: AlertGroup) -> None:
        cat = group.category
        handler = getattr(self, f"_explain_{cat}", None) or self._explain_default
        title, what, why, attack = handler(group)
        info = self.rule_kb.get(group.rule_id) if self.rule_kb else None
        if info and info.explanation and info.explanation not in why:
            why = f"{why} {info.explanation}".strip()
        group.title = title
        group.what_happened = what
        group.why_it_matters = why
        group.possible_attack = attack
        group.evidence = self._evidence(group)
        group.assessment = self.assessment(group)

    # ------------------------------------------------------------------ assessment (English keys)
    def assessment(self, group: AlertGroup) -> str:
        if group.ioc_verdict == "malicious" or (group.vt_positives or 0) >= 5:
            return "Confirmed malicious indicator"
        if group.success_after_failures and group.category in (C.AUTH_SUCCESS.value,):
            return "Potential compromise"
        if group.chain_ids:
            return "Possible attack chain"
        if group.fp_probability >= 0.6:
            return "Likely benign / possible false positive"
        if group.category in (C.AUTH_FAILURE.value, C.BRUTE_FORCE.value) and group.peak_count >= self.threshold:
            return "Likely brute-force activity"
        if group.severity in ("critical", "high"):
            return "Possible attack" if group.category not in (C.VULNERABILITY.value, C.POLICY.value) \
                else "Suspicious activity"
        if group.severity == "medium":
            return "Suspicious activity"
        if group.vendor == "generic" and group.rule_level <= 2:
            return "Insufficient evidence"
        return "Informational event"

    # ------------------------------------------------------------------ evidence (facts only)
    def _evidence(self, group: AlertGroup) -> list[str]:
        ev = [tr("{events} of rule {rule} \"{description}\" (Wazuh level {level}){period}.",
                 events=n(group.count, "event"), rule=group.rule_id, description=group.rule_description,
                 level=group.rule_level, period=_period(group))]
        if group.agent_name:
            ev.append(tr("Host: {host}.", host=group.agent_name + (f" ({group.agent_ip})" if group.agent_ip else "")))
        if group.src_ips:
            ev.append(tr("Source IP(s): {ips}.", ips=truncate_list(group.src_ips)))
        if group.users:
            ev.append(tr("Account(s): {users}.", users=truncate_list(group.users, 8)))
        if group.processes:
            ev.append(tr("Process(es): {processes}.", processes=truncate_list(group.processes, 3)))
        if group.command_lines:
            ev.append(tr("Command line: {command}", command=group.command_lines[0][:300]))
        if group.file_paths:
            ev.append(tr("File(s): {files}.", files=truncate_list(group.file_paths, 3)))
        if group.file_hash:
            ev.append(tr("File hash: {hash}.", hash=group.file_hash))
        if group.cves:
            cvss = tr(" (CVSS {cvss})", cvss=f"{group.cvss:.1f}") if group.cvss is not None else ""
            ev.append(tr("Vulnerabilities: {cves}{cvss}.", cves=truncate_list(group.cves), cvss=cvss))
        if group.packages:
            ev.append(tr("Package(s): {packages}.", packages=truncate_list(group.packages, 3)))
        if group.vt_positives is not None:
            ev.append(tr("VirusTotal detections: {positives}/{total}.", positives=group.vt_positives,
                         total=group.vt_total or "?"))
        if group.success_after_failures and group.category == C.AUTH_SUCCESS.value:
            ev.append(tr("Preceded by {count} failed authentications from the same source/account.",
                         count=num(group.failures_before_success)))
        elif group.success_after_failures:
            ev.append(tr("A successful authentication from the same source/account followed these failures."))
        if group.ioc_verdict in ("malicious", "suspicious"):
            ev.append(tr("Threat intelligence verdict: {verdict} ({sources}).", verdict=tr(group.ioc_verdict),
                         sources=", ".join(group.ioc_verdict_sources[:3])))
        if group.kev:
            ev.append(tr("{cve} is listed in the CISA Known Exploited Vulnerabilities catalog.", cve=group.cve))
        return ev

    # ------------------------------------------------------------------ per-category templates
    def _explain_auth_failure(self, g: AlertGroup):
        users = len(g.users)
        bulk = g.peak_count >= self.threshold or g.category == C.BRUTE_FORCE.value
        if g.src_ip and bulk:
            title = tr("Repeated failed logins from {ip}", ip=g.src_ip)
        else:
            title = tr("Failed login on {host}", host=_host(g))
        targets = tr(", targeting {accounts} ({names})", accounts=n(users, "account"),
                     names=truncate_list(g.users, 5)) if users else ""
        what = tr("{attempts} were recorded on {host} from {source}{period}{targets}.",
                  attempts=n(g.count, "failed authentication attempt"), host=_host(g), source=_src(g),
                  period=_period(g), targets=targets)
        if "non-existent" in g.rule_description.lower() or "invalid" in g.rule_description.lower():
            what += " " + tr("Some or all of the accounts used do not exist on the host.")
        if bulk:
            why = tr("Many failures from one source in a short time are typical of password guessing or username "
                     "enumeration.") + " "
        elif g.count >= self.threshold:
            why = tr("The failures are spread out over time (at most {peak} in one correlation window), which is more "
                     "typical of a misconfigured service, a periodic job or a scanner than of brute force.",
                     peak=g.peak_count) + " "
        else:
            why = tr("Occasional failed logins are common and usually harmless.") + " "
        if g.success_after_failures:
            why += tr("A successful login from the same source/account followed, so the attempts may have "
                      "succeeded.") + " "
        attack = tr("Likely brute-force / password-guessing activity (Credential Access).") if bulk else \
            tr("Insufficient evidence of an attack from this event alone.")
        if g.success_after_failures:
            attack = tr("Possible successful brute-force attack leading to account compromise.")
        return title, what, why.strip(), attack

    _explain_brute_force = _explain_auth_failure

    def _explain_auth_success(self, g: AlertGroup):
        if g.user:
            title = tr("Successful login to {host} as {user}", host=_host(g), user=g.user)
        else:
            title = tr("Successful login to {host}", host=_host(g))
        account = tr(" with account '{user}'", user=g.user) if g.user else ""
        what = tr("{logins} to {host}{account} from {source}{period}.", logins=n(g.count, "successful authentication"),
                  host=_host(g), account=account, source=_src(g), period=_period(g))
        if g.success_after_failures:
            why = tr("The login came after {count} failed attempts from the same source or account. This sequence is a "
                     "classic indicator of a successful brute-force attack.", count=num(g.failures_before_success))
            attack = tr("Potential compromise: valid account obtained by password guessing (Initial Access).")
        elif g.src_external:
            why = tr("Logins from external addresses deserve verification, especially for privileged accounts.")
            attack = tr("Suspicious activity if the user does not normally connect from this address.")
        else:
            why = tr("Successful logins are normally legitimate user or service activity.")
            attack = tr("No attack indicated by this event alone.")
        return title, what, why, attack

    def _explain_execution(self, g: AlertGroup):
        proc = g.processes[0] if g.processes else tr("a process")
        title = tr("Suspicious command execution on {host}", host=_host(g))
        by = tr(" by '{user}'", user=g.user) if g.user else ""
        command = (" " + tr("Command: {command}", command=g.command_lines[0][:200])) if g.command_lines else ""
        what = tr("{process} was executed on {host}{by}{period}.", process=proc, host=_host(g), by=by,
                  period=_period(g)) + command
        why = tr("The command line contains patterns frequently used by attackers (encoded commands, download cradles, "
                 "hidden windows or proxy execution). Legitimate administration scripts sometimes use them too.")
        attack = tr("Possible malicious code execution (Execution) - verify whether IT launched this command.")
        return title, what, why, attack

    def _explain_process_activity(self, g: AlertGroup):
        proc = g.processes[0] if g.processes else tr("a process")
        return (tr("Process activity on {host}", host=_host(g)),
                tr("{process} activity was recorded on {host}{period}.", process=proc, host=_host(g), period=_period(g)),
                tr("Process events are mainly useful as context for other alerts."),
                tr("No attack indicated by this event alone."))

    def _explain_credential_access(self, g: AlertGroup):
        title = tr("Possible credential theft on {host}", host=_host(g))
        detail = f": {g.command_lines[0][:200]}" if g.command_lines else "."
        what = tr("Activity associated with credential access was recorded on {host}{period}", host=_host(g),
                  period=_period(g)) + detail
        why = tr("Tools that read LSASS memory or dump password hashes let an attacker reuse credentials on other "
                 "systems. This is usually hands-on-keyboard attacker activity.")
        attack = tr("Possible credential dumping (Credential Access) followed by lateral movement.")
        return title, what, why, attack

    def _explain_impact(self, g: AlertGroup):
        title = tr("Destructive activity on {host}", host=_host(g))
        detail = f": {g.command_lines[0][:200]}" if g.command_lines else "."
        what = tr("A command associated with destroying backups or data was run on {host}{period}", host=_host(g),
                  period=_period(g)) + detail
        why = tr("Deleting shadow copies or backups is a common step immediately before ransomware encryption.")
        attack = tr("Possible ransomware preparation (Impact).")
        return title, what, why, attack

    def _explain_defense_evasion(self, g: AlertGroup):
        title = tr("Security controls altered on {host}", host=_host(g))
        what = tr("Activity that disables security tools or removes logs was recorded on {host}{period}.",
                  host=_host(g), period=_period(g))
        why = tr("Attackers clear logs or stop security agents to hide their activity. It can also be maintenance.")
        attack = tr("Possible defense evasion - check what happened just before this event.")
        return title, what, why, attack

    def _explain_persistence(self, g: AlertGroup):
        title = tr("Persistence mechanism created on {host}", host=_host(g))
        detail = f": {g.command_lines[0][:200]}" if g.command_lines else "."
        what = tr("A scheduled task, service or autostart entry was created on {host}{period}", host=_host(g),
                  period=_period(g)) + detail
        why = tr("Persistence lets malware or an attacker survive reboots. Software installers also create such "
                 "entries.")
        attack = tr("Possible persistence (Persistence) if the entry is not linked to approved software.")
        return title, what, why, attack

    def _explain_account_change(self, g: AlertGroup):
        title = tr("Account change on {host}", host=_host(g)) + (f": {g.user}" if g.user else "")
        target = tr(" for '{user}'", user=g.user) if g.user else ""
        what = tr("An account or group change was recorded on {host}{target}{period}: {description}.", host=_host(g),
                  target=target, period=_period(g), description=g.rule_description)
        why = tr("Creating accounts or adding users to privileged groups is a common way to keep access.")
        attack = tr("Possible persistence through account manipulation if the change was not approved.")
        return title, what, why, attack

    def _explain_privilege_escalation(self, g: AlertGroup):
        title = tr("Privileged execution on {host}", host=_host(g))
        by = tr(" by '{user}'", user=g.user) if g.user else ""
        what = tr("{actions}{by} on {host}{period}: {description}.", actions=n(g.count, "privileged action"), by=by,
                  host=_host(g), period=_period(g), description=g.rule_description)
        why = tr("Privilege use is normal for administrators but important when the account is unexpected.")
        attack = tr("Suspicious only if the user is not an authorised administrator.")
        return title, what, why, attack

    def _explain_network_c2(self, g: AlertGroup):
        title = tr("Suspicious outbound connection from {host}", host=_host(g))
        what = tr("{process} on {host} connected to external address(es) {destinations}{period}.",
                  process=g.processes[0] if g.processes else tr("A process"), host=_host(g),
                  destinations=truncate_list(g.dst_ips, 3), period=_period(g))
        why = tr("Script interpreters and system binaries rarely need direct Internet connections; such traffic can be "
                 "malware contacting its command-and-control server or downloading tools.")
        attack = tr("Possible command-and-control or tool download (Command and Control).")
        return title, what, why, attack

    def _explain_lateral_movement(self, g: AlertGroup):
        return (tr("Possible lateral movement involving {host}", host=_host(g)),
                tr("Remote execution / remote service activity was recorded on {host}{period}.", host=_host(g),
                   period=_period(g)),
                tr("Attackers use remote services and admin shares to move between systems."),
                tr("Possible lateral movement (Lateral Movement)."))

    def _explain_scan(self, g: AlertGroup):
        title = tr("Scanning activity from {source}", source=g.src_ip or tr("unknown source"))
        what = tr("{events} indicating probing of {host} from {source}{period}.", events=n(g.count, "event"),
                  host=_host(g), source=_src(g), period=_period(g))
        why = tr("Scans map exposed services and vulnerabilities and often precede targeted attacks. Internet-facing "
                 "systems receive background scanning constantly.")
        attack = tr("Reconnaissance - usually low risk unless followed by exploitation or successful logins.")
        return title, what, why, attack

    def _explain_web_attack(self, g: AlertGroup):
        title = tr("Web attack attempts against {host}", host=_host(g))
        what = tr("{requests} from {source} against {host}{period}: {description}.",
                  requests=n(g.count, "malicious web request"), source=_src(g), host=_host(g), period=_period(g),
                  description=g.rule_description)
        why = tr("Injection and traversal attempts try to exploit the web application. Most are automated and fail, "
                 "but a successful response (HTTP 200) may mean the application processed the payload.")
        attack = tr("Possible exploitation attempt of a public-facing application (Initial Access).")
        return title, what, why, attack

    def _explain_malware(self, g: AlertGroup):
        file_ = g.file_paths[0] if g.file_paths else tr("a file")
        title = tr("Malicious file detected on {host}", host=_host(g))
        what = tr("{file} on {host} was flagged{period}: {description}.", file=file_, host=_host(g), period=_period(g),
                  description=g.rule_description)
        if g.vt_positives is not None:
            what += " " + tr("VirusTotal reports {positives}/{total} detections.", positives=g.vt_positives,
                             total=g.vt_total or "?")
        why = tr("A malicious file on a host can lead to execution, data theft or ransomware if it is run.")
        if (g.vt_positives or 0) >= 5 or g.ioc_verdict == "malicious":
            attack = tr("Confirmed malicious indicator - determine whether the file was executed.")
        else:
            attack = tr("Possible malware - verify the detection.")
        return title, what, why, attack

    def _explain_fim(self, g: AlertGroup):
        title = tr("File change on {host}", host=_host(g))
        what = tr("File integrity monitoring recorded {changes} to {files} on {host}{period}.",
                  changes=n(g.count, "change"), files=truncate_list(g.file_paths, 2), host=_host(g), period=_period(g))
        why = tr("Unexpected changes to binaries or configuration can indicate tampering; most are updates or admin "
                 "work.")
        attack = tr("Suspicious only if no approved change explains it.")
        return title, what, why, attack

    def _explain_vulnerability(self, g: AlertGroup):
        title = tr("{cve} on {host}", cve=g.cve or tr("Vulnerability"), host=_host(g))
        cvss = tr(" (CVSS {cvss})", cvss=f"{g.cvss:.1f}") if g.cvss is not None else ""
        what = tr("{host} has {package} affected by {cves}{cvss}.", host=_host(g),
                  package=truncate_list(g.packages, 2) if g.packages else tr("a package"),
                  cves=truncate_list(g.cves, 3), cvss=cvss)
        why = tr("Unpatched vulnerabilities can be exploited to gain access or elevate privileges.")
        if g.kev:
            why += " " + tr("This CVE is known to be actively exploited in the wild.")
        attack = tr("Exposure, not an attack: no exploitation was observed in these logs.")
        return title, what, why, attack

    def _explain_policy(self, g: AlertGroup):
        return (tr("Configuration check on {host}", host=_host(g)),
                tr("{description} on {host}{period}.", description=g.rule_description, host=_host(g), period=_period(g)),
                tr("Hardening gaps increase the attack surface but are not attacks themselves."),
                tr("No attack indicated."))

    def _explain_system(self, g: AlertGroup):
        return (tr("Agent/system event on {host}", host=_host(g)),
                tr("{description} on {host}{period}.", description=g.rule_description, host=_host(g), period=_period(g)),
                tr("Operational events are normally benign but explain gaps in monitoring."),
                tr("No attack indicated."))

    def _explain_network(self, g: AlertGroup):
        return (tr("Network activity on {host}", host=_host(g)),
                tr("{events} involving {source} on {host}{period}: {description}.", events=n(g.count, "network event"),
                   source=_src(g), host=_host(g), period=_period(g), description=g.rule_description),
                tr("Network events are useful context; in bulk they may indicate scanning."),
                tr("Insufficient evidence of an attack from these events alone."))

    def _explain_default(self, g: AlertGroup):
        return (g.rule_description[:120] or tr("Rule {rule}", rule=g.rule_id),
                tr("{events} of rule {rule} on {host}{period}: {description}.", events=n(g.count, "event"),
                   rule=g.rule_id, host=_host(g), period=_period(g), description=g.rule_description),
                tr("Wazuh assigned level {level}/15 to this rule.", level=g.rule_level),
                tr("Insufficient evidence to describe a specific attack."))
