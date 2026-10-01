"""Plain-language explanations that keep *facts* separate from *analysis*.

``evidence`` contains only observations taken from the logs.  ``what_happened`` describes
the observed events, ``why_it_matters`` / ``possible_attack`` contain analytical
interpretation, worded cautiously ("possible", "likely", "suspicious") unless confirmed by
a malicious indicator.  The analyzer never claims a system "has been hacked".
"""

from __future__ import annotations

from app.models.analysis import AlertGroup
from app.models.categories import Category
from app.utils.text import plural, truncate_list
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
        return "an unknown source"
    return f"{'external' if group.src_external else 'internal'} IP {group.src_ip}"


def _host(group: AlertGroup) -> str:
    return group.agent_name or "an unidentified host"


def _period(group: AlertGroup) -> str:
    if group.first_ts is None:
        return ""
    if group.count == 1 or group.last_ts == group.first_ts:
        return f" at {fmt_ts(group.first_ts)}"
    return f" between {fmt_ts(group.first_ts)} and {fmt_ts(group.last_ts)} " \
           f"({fmt_duration((group.last_ts or 0) - group.first_ts)})"


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

    # ------------------------------------------------------------------ assessment
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
        ev = [f"{plural(group.count, 'event')} of rule {group.rule_id} \"{group.rule_description}\""
              f" (Wazuh level {group.rule_level}){_period(group)}."]
        if group.agent_name:
            ev.append(f"Host: {group.agent_name}" + (f" ({group.agent_ip})" if group.agent_ip else "") + ".")
        if group.src_ips:
            ev.append(f"Source IP(s): {truncate_list(group.src_ips)}.")
        if group.users:
            ev.append(f"Account(s): {truncate_list(group.users, 8)}.")
        if group.processes:
            ev.append(f"Process(es): {truncate_list(group.processes, 3)}.")
        if group.command_lines:
            ev.append(f"Command line: {group.command_lines[0][:300]}")
        if group.file_paths:
            ev.append(f"File(s): {truncate_list(group.file_paths, 3)}.")
        if group.file_hash:
            ev.append(f"File hash: {group.file_hash}.")
        if group.cves:
            ev.append(f"Vulnerabilities: {truncate_list(group.cves)}" +
                      (f" (CVSS {group.cvss:.1f})" if group.cvss is not None else "") + ".")
        if group.packages:
            ev.append(f"Package(s): {truncate_list(group.packages, 3)}.")
        if group.vt_positives is not None:
            ev.append(f"VirusTotal detections: {group.vt_positives}/{group.vt_total or '?'}.")
        if group.success_after_failures and group.category == C.AUTH_SUCCESS.value:
            ev.append(f"Preceded by {group.failures_before_success} failed authentications from the same source/account.")
        elif group.success_after_failures:
            ev.append("A successful authentication from the same source/account followed these failures.")
        if group.ioc_verdict in ("malicious", "suspicious"):
            ev.append(f"Threat intelligence verdict: {group.ioc_verdict} ({', '.join(group.ioc_verdict_sources[:3])}).")
        if group.kev:
            ev.append(f"{group.cve} is listed in the CISA Known Exploited Vulnerabilities catalog.")
        return ev

    # ------------------------------------------------------------------ per-category templates
    def _explain_auth_failure(self, g: AlertGroup):
        users = len(g.users)
        bulk = g.peak_count >= self.threshold or g.category == C.BRUTE_FORCE.value
        title = (f"Repeated failed logins from {g.src_ip}" if g.src_ip and bulk else
                 f"Failed login on {_host(g)}")
        what = (f"{plural(g.count, 'failed authentication attempt')} were recorded on {_host(g)} from {_src(g)}"
                f"{_period(g)}" + (f", targeting {plural(users, 'account')} ({truncate_list(g.users, 5)})"
                                    if users else "") + ".")
        if "non-existent" in g.rule_description.lower() or "invalid" in g.rule_description.lower():
            what += " Some or all of the accounts used do not exist on the host."
        if bulk:
            why = "Many failures from one source in a short time are typical of password guessing or username enumeration. "
        elif g.count >= self.threshold:
            why = (f"The failures are spread out over time (at most {g.peak_count} in one correlation window), which is "
                   "more typical of a misconfigured service, a periodic job or a scanner than of brute force. ")
        else:
            why = "Occasional failed logins are common and usually harmless. "
        if g.success_after_failures:
            why += "A successful login from the same source/account followed, so the attempts may have succeeded. "
        attack = ("Likely brute-force / password-guessing activity (Credential Access)." if bulk else
                  "Insufficient evidence of an attack from this event alone.")
        if g.success_after_failures:
            attack = "Possible successful brute-force attack leading to account compromise."
        return title, what, why.strip(), attack

    _explain_brute_force = _explain_auth_failure

    def _explain_auth_success(self, g: AlertGroup):
        title = f"Successful login to {_host(g)}" + (f" as {g.user}" if g.user else "")
        what = (f"{plural(g.count, 'successful authentication')} to {_host(g)}" +
                (f" with account '{g.user}'" if g.user else "") + f" from {_src(g)}{_period(g)}.")
        if g.success_after_failures:
            why = (f"The login came after {g.failures_before_success} failed attempts from the same source or "
                   "account. This sequence is a classic indicator of a successful brute-force attack.")
            attack = "Potential compromise: valid account obtained by password guessing (Initial Access)."
        elif g.src_external:
            why = "Logins from external addresses deserve verification, especially for privileged accounts."
            attack = "Suspicious activity if the user does not normally connect from this address."
        else:
            why = "Successful logins are normally legitimate user or service activity."
            attack = "No attack indicated by this event alone."
        return title, what, why, attack

    def _explain_execution(self, g: AlertGroup):
        proc = g.processes[0] if g.processes else "a process"
        title = f"Suspicious command execution on {_host(g)}"
        what = (f"{proc} was executed on {_host(g)}" + (f" by '{g.user}'" if g.user else "") +
                f"{_period(g)}." + (f" Command: {g.command_lines[0][:200]}" if g.command_lines else ""))
        why = ("The command line contains patterns frequently used by attackers (encoded commands, download "
               "cradles, hidden windows or proxy execution). Legitimate administration scripts sometimes use them too.")
        attack = "Possible malicious code execution (Execution) - verify whether IT launched this command."
        return title, what, why, attack

    def _explain_process_activity(self, g: AlertGroup):
        proc = g.processes[0] if g.processes else "a process"
        return (f"Process activity on {_host(g)}", f"{proc} activity was recorded on {_host(g)}{_period(g)}.",
                "Process events are mainly useful as context for other alerts.",
                "No attack indicated by this event alone.")

    def _explain_credential_access(self, g: AlertGroup):
        title = f"Possible credential theft on {_host(g)}"
        what = (f"Activity associated with credential access was recorded on {_host(g)}{_period(g)}" +
                (f": {g.command_lines[0][:200]}" if g.command_lines else ".") )
        why = ("Tools that read LSASS memory or dump password hashes let an attacker reuse credentials on other "
               "systems. This is usually hands-on-keyboard attacker activity.")
        attack = "Possible credential dumping (Credential Access) followed by lateral movement."
        return title, what, why, attack

    def _explain_impact(self, g: AlertGroup):
        title = f"Destructive activity on {_host(g)}"
        what = (f"A command associated with destroying backups or data was run on {_host(g)}{_period(g)}" +
                (f": {g.command_lines[0][:200]}" if g.command_lines else "."))
        why = "Deleting shadow copies or backups is a common step immediately before ransomware encryption."
        attack = "Possible ransomware preparation (Impact)."
        return title, what, why, attack

    def _explain_defense_evasion(self, g: AlertGroup):
        title = f"Security controls altered on {_host(g)}"
        what = f"Activity that disables security tools or removes logs was recorded on {_host(g)}{_period(g)}."
        why = "Attackers clear logs or stop security agents to hide their activity. It can also be maintenance."
        attack = "Possible defense evasion - check what happened just before this event."
        return title, what, why, attack

    def _explain_persistence(self, g: AlertGroup):
        title = f"Persistence mechanism created on {_host(g)}"
        what = (f"A scheduled task, service or autostart entry was created on {_host(g)}{_period(g)}" +
                (f": {g.command_lines[0][:200]}" if g.command_lines else "."))
        why = "Persistence lets malware or an attacker survive reboots. Software installers also create such entries."
        attack = "Possible persistence (Persistence) if the entry is not linked to approved software."
        return title, what, why, attack

    def _explain_account_change(self, g: AlertGroup):
        title = f"Account change on {_host(g)}" + (f": {g.user}" if g.user else "")
        what = (f"An account or group change was recorded on {_host(g)}" + (f" for '{g.user}'" if g.user else "") +
                f"{_period(g)}: {g.rule_description}.")
        why = "Creating accounts or adding users to privileged groups is a common way to keep access."
        attack = "Possible persistence through account manipulation if the change was not approved."
        return title, what, why, attack

    def _explain_privilege_escalation(self, g: AlertGroup):
        title = f"Privileged execution on {_host(g)}"
        what = (f"{plural(g.count, 'privileged action')}" + (f" by '{g.user}'" if g.user else "") +
                f" on {_host(g)}{_period(g)}: {g.rule_description}.")
        why = "Privilege use is normal for administrators but important when the account is unexpected."
        attack = "Suspicious only if the user is not an authorised administrator."
        return title, what, why, attack

    def _explain_network_c2(self, g: AlertGroup):
        dest = truncate_list(g.dst_ips, 3)
        title = f"Suspicious outbound connection from {_host(g)}"
        what = (f"{g.processes[0] if g.processes else 'A process'} on {_host(g)} connected to external address(es) "
                f"{dest}{_period(g)}.")
        why = ("Script interpreters and system binaries rarely need direct Internet connections; such traffic can be "
               "malware contacting its command-and-control server or downloading tools.")
        attack = "Possible command-and-control or tool download (Command and Control)."
        return title, what, why, attack

    def _explain_lateral_movement(self, g: AlertGroup):
        return (f"Possible lateral movement involving {_host(g)}",
                f"Remote execution / remote service activity was recorded on {_host(g)}{_period(g)}.",
                "Attackers use remote services and admin shares to move between systems.",
                "Possible lateral movement (Lateral Movement).")

    def _explain_scan(self, g: AlertGroup):
        title = f"Scanning activity from {g.src_ip or 'unknown source'}"
        what = f"{plural(g.count, 'event')} indicating probing of {_host(g)} from {_src(g)}{_period(g)}."
        why = ("Scans map exposed services and vulnerabilities and often precede targeted attacks. Internet-facing "
               "systems receive background scanning constantly.")
        attack = "Reconnaissance - usually low risk unless followed by exploitation or successful logins."
        return title, what, why, attack

    def _explain_web_attack(self, g: AlertGroup):
        title = f"Web attack attempts against {_host(g)}"
        what = f"{plural(g.count, 'malicious web request')} from {_src(g)} against {_host(g)}{_period(g)}: " \
               f"{g.rule_description}."
        why = ("Injection and traversal attempts try to exploit the web application. Most are automated and fail, "
               "but a successful response (HTTP 200) may mean the application processed the payload.")
        attack = "Possible exploitation attempt of a public-facing application (Initial Access)."
        return title, what, why, attack

    def _explain_malware(self, g: AlertGroup):
        file_ = g.file_paths[0] if g.file_paths else "a file"
        title = f"Malicious file detected on {_host(g)}"
        what = f"{file_} on {_host(g)} was flagged{_period(g)}: {g.rule_description}."
        if g.vt_positives is not None:
            what += f" VirusTotal reports {g.vt_positives}/{g.vt_total or '?'} detections."
        why = "A malicious file on a host can lead to execution, data theft or ransomware if it is run."
        attack = ("Confirmed malicious indicator - determine whether the file was executed."
                  if (g.vt_positives or 0) >= 5 or g.ioc_verdict == "malicious"
                  else "Possible malware - verify the detection.")
        return title, what, why, attack

    def _explain_fim(self, g: AlertGroup):
        file_ = truncate_list(g.file_paths, 2)
        title = f"File change on {_host(g)}"
        what = f"File integrity monitoring recorded {plural(g.count, 'change')} to {file_} on {_host(g)}{_period(g)}."
        why = "Unexpected changes to binaries or configuration can indicate tampering; most are updates or admin work."
        attack = "Suspicious only if no approved change explains it."
        return title, what, why, attack

    def _explain_vulnerability(self, g: AlertGroup):
        title = f"{g.cve or 'Vulnerability'} on {_host(g)}"
        what = (f"{_host(g)} has {truncate_list(g.packages, 2) if g.packages else 'a package'} affected by "
                f"{truncate_list(g.cves, 3)}" + (f" (CVSS {g.cvss:.1f})" if g.cvss is not None else "") + ".")
        why = "Unpatched vulnerabilities can be exploited to gain access or elevate privileges."
        if g.kev:
            why += " This CVE is known to be actively exploited in the wild."
        attack = "Exposure, not an attack: no exploitation was observed in these logs."
        return title, what, why, attack

    def _explain_policy(self, g: AlertGroup):
        return (f"Configuration check on {_host(g)}", f"{g.rule_description} on {_host(g)}{_period(g)}.",
                "Hardening gaps increase the attack surface but are not attacks themselves.",
                "No attack indicated.")

    def _explain_system(self, g: AlertGroup):
        return (f"Agent/system event on {_host(g)}", f"{g.rule_description} on {_host(g)}{_period(g)}.",
                "Operational events are normally benign but explain gaps in monitoring.",
                "No attack indicated.")

    def _explain_network(self, g: AlertGroup):
        return (f"Network activity on {_host(g)}",
                f"{plural(g.count, 'network event')} involving {_src(g)} on {_host(g)}{_period(g)}: "
                f"{g.rule_description}.",
                "Network events are useful context; in bulk they may indicate scanning.",
                "Insufficient evidence of an attack from these events alone.")

    def _explain_default(self, g: AlertGroup):
        return (g.rule_description[:120] or f"Rule {g.rule_id}",
                f"{plural(g.count, 'event')} of rule {g.rule_id} on {_host(g)}{_period(g)}: {g.rule_description}.",
                f"Wazuh assigned level {g.rule_level}/15 to this rule.",
                "Insufficient evidence to describe a specific attack.")
