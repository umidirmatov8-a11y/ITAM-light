"""Attack-chain detection.

Alerts on each host are converted into kill-chain *stages*, consecutive alerts of the same
stage are merged into segments, and segments separated by less than the correlation window
are joined.  A chain is reported only when

* it contains at least one *anchor* (clearly suspicious behaviour such as brute force,
  malware, credential dumping, encoded PowerShell, C2 or destructive commands), and
* the stages progress through at least ``min_chain_stages`` distinct kill-chain phases in
  order (longest increasing subsequence), **or** a successful login after repeated
  failures is followed by post-compromise activity.

Ordinary activity (internal logins without failures, FIM, policy checks) never forms a chain.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from app.models.analysis import AlertGroup, AttackChain, ChainStage
from app.models.categories import Category

C = Category

# category -> (stage key, order, label)
STAGES: dict[str, tuple[str, int, str]] = {
    C.SCAN.value: ("reconnaissance", 0, "Reconnaissance"),
    C.WEB_ATTACK.value: ("exploit_attempt", 1, "Exploitation attempt"),
    C.AUTH_FAILURE.value: ("credential_attack", 1, "Credential attack (failed logins)"),
    C.BRUTE_FORCE.value: ("credential_attack", 1, "Credential attack (failed logins)"),
    C.AUTH_SUCCESS.value: ("initial_access", 2, "Initial Access (successful login)"),
    C.EXECUTION.value: ("execution", 3, "Execution"),
    C.MALWARE.value: ("execution", 3, "Execution (malicious file)"),
    C.PRIVILEGE_ESCALATION.value: ("privilege_escalation", 4, "Privilege Escalation"),
    C.ACCOUNT_CHANGE.value: ("persistence", 4, "Persistence (account change)"),
    C.PERSISTENCE.value: ("persistence", 4, "Persistence"),
    C.DEFENSE_EVASION.value: ("defense_evasion", 4, "Defense Evasion"),
    C.CREDENTIAL_ACCESS.value: ("credential_access", 5, "Credential Access"),
    C.LATERAL_MOVEMENT.value: ("lateral_movement", 6, "Lateral Movement"),
    C.NETWORK_C2.value: ("command_and_control", 6, "Command and Control"),
    C.IMPACT.value: ("impact", 7, "Impact"),
}

ANCHOR_CATEGORIES = {C.BRUTE_FORCE.value, C.MALWARE.value, C.CREDENTIAL_ACCESS.value, C.IMPACT.value,
                     C.NETWORK_C2.value, C.EXECUTION.value, C.DEFENSE_EVASION.value, C.WEB_ATTACK.value,
                     C.LATERAL_MOVEMENT.value}

SCENARIO_TACTICS = {
    "reconnaissance": "Reconnaissance",
    "exploit_attempt": "Initial Access",
    "credential_attack": "Credential Access (brute force)",
    "initial_access": "Initial Access",
    "execution": "Execution",
    "privilege_escalation": "Privilege Escalation",
    "persistence": "Persistence",
    "defense_evasion": "Defense Evasion",
    "credential_access": "Credential Access (credential dumping)",
    "lateral_movement": "Lateral Movement",
    "command_and_control": "Command & Control",
    "impact": "Impact",
}


@dataclass
class _Segment:
    stage: str
    order: int
    label: str
    category: str
    first_ts: float
    last_ts: float
    count: int = 0
    group_ids: set[int] = field(default_factory=set)
    src_ips: set[str] = field(default_factory=set)
    users: set[str] = field(default_factory=set)
    anchor: bool = False


@dataclass
class _FailState:
    """Failures from one source/account; ``recent`` is a sliding window used for burst detection."""

    total: int = 0
    last_ts: float = 0.0
    recent: deque = field(default_factory=lambda: deque(maxlen=10_000))
    group_ids: set[int] = field(default_factory=set)

    def add(self, ts: float, window: float) -> int:
        self.total += 1
        self.last_ts = ts
        self.recent.append(ts)
        while self.recent and ts - self.recent[0] > window:
            self.recent.popleft()
        return len(self.recent)


def _lis_indices(orders: list[int]) -> list[int]:
    """Indices of a longest strictly increasing subsequence (O(n^2), n is small)."""
    n = len(orders)
    if n == 0:
        return []
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if orders[j] < orders[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    end = max(range(n), key=lambda i: best[i])
    seq = []
    while end != -1:
        seq.append(end)
        end = prev[end]
    return list(reversed(seq))


class ChainDetector:
    def __init__(self, window_minutes: int = 60, min_stages: int = 3, bruteforce_threshold: int = 5,
                 success_window_minutes: int = 60, is_external=None):
        self.window = window_minutes * 60
        self.min_stages = min_stages
        self.threshold = bruteforce_threshold
        self.success_window = success_window_minutes * 60
        self.is_external = is_external or (lambda ip: False)
        self.chains: list[AttackChain] = []
        self.success_pairs: list[tuple[int, set[int], int]] = []  # (success group, failure groups, failures)

    def run(self, rows: Iterable[tuple], groups_by_id: dict[int, AlertGroup]) -> list[AttackChain]:
        """``rows`` = (agent, ts, category, group_id, src_ip, user) sorted by agent, ts."""
        current_agent = None
        segments: list[_Segment] = []
        fails_by_src: dict[str, _FailState] = {}
        fails_by_user: dict[str, _FailState] = {}
        for agent, ts, category, group_id, src_ip, user in rows:
            if ts is None:
                continue
            if agent != current_agent:
                if current_agent is not None:
                    self._finish_agent(current_agent, segments, groups_by_id)
                current_agent = agent
                segments = []
                fails_by_src = {}
                fails_by_user = {}
            stage_info = STAGES.get(category)
            if stage_info is None:
                continue
            src_ip = src_ip or ""
            user = user or ""
            anchor = category in ANCHOR_CATEGORIES
            if category in (C.AUTH_FAILURE.value, C.BRUTE_FORCE.value):
                burst = 0
                for table, key in ((fails_by_src, src_ip), (fails_by_user, user)):
                    if not key:
                        continue
                    state = table.get(key)
                    if state is None or ts - state.last_ts > self.success_window:
                        state = table[key] = _FailState()
                    burst = max(burst, state.add(ts, self.window))
                    if len(state.group_ids) < 50:
                        state.group_ids.add(group_id)
                # Isolated failures (typos, slow periodic scanners) are not part of an attack narrative.
                if burst < self.threshold and category != C.BRUTE_FORCE.value:
                    continue
                anchor = True
            elif category == C.AUTH_SUCCESS.value:
                state = fails_by_src.get(src_ip) if src_ip else None
                if state is None and user:
                    state = fails_by_user.get(user)
                matched = state is not None and len(state.recent) >= self.threshold and \
                    0 <= ts - state.last_ts <= self.success_window
                if matched:
                    self.success_pairs.append((group_id, set(state.group_ids), state.total))
                    anchor = True
                elif not self.is_external(src_ip):
                    continue  # ordinary internal login - not part of an attack narrative
            stage, order, label = stage_info
            last = segments[-1] if segments else None
            if last and last.stage == stage and ts - last.last_ts <= self.window:
                seg = last
            else:
                seg = _Segment(stage, order, label, category, ts, ts)
                segments.append(seg)
            seg.last_ts = max(seg.last_ts, ts)
            seg.count += 1
            seg.anchor = seg.anchor or anchor
            if len(seg.group_ids) < 200:
                seg.group_ids.add(group_id)
            if src_ip and len(seg.src_ips) < 20:
                seg.src_ips.add(src_ip)
            if user and len(seg.users) < 20:
                seg.users.add(user)
            if len(segments) > 5000:  # bound memory on extremely noisy hosts
                self._finish_agent(current_agent, segments[:-1], groups_by_id)
                segments = segments[-1:]
        if current_agent is not None:
            self._finish_agent(current_agent, segments, groups_by_id)
        self._mark_success_pairs(groups_by_id)
        return self.chains

    def _finish_agent(self, agent: str, segments: list[_Segment], groups_by_id: dict[int, AlertGroup]) -> None:
        window: list[_Segment] = []
        for seg in segments:
            if window and seg.first_ts - max(s.last_ts for s in window[-3:]) > self.window:
                self._evaluate(agent, window, groups_by_id)
                window = []
            window.append(seg)
        if window:
            self._evaluate(agent, window, groups_by_id)

    def _evaluate(self, agent: str, window: list[_Segment], groups_by_id: dict[int, AlertGroup]) -> None:
        if not any(s.anchor for s in window):
            return
        # First occurrence of each stage, in time order.
        firsts: list[_Segment] = []
        seen: set[str] = set()
        for seg in window:
            if seg.stage not in seen:
                seen.add(seg.stage)
                firsts.append(seg)
        orders = [s.order for s in firsts]
        lis = [firsts[i] for i in _lis_indices(orders)]
        success_after_fail = any(
            s.stage == "initial_access" and s.anchor for s in window
        )
        post_compromise = any(s.order >= 3 for s in window)
        qualifies = len(lis) >= self.min_stages or (success_after_fail and post_compromise and len(lis) >= 2)
        if not qualifies:
            return
        lis_stages = {s.stage for s in lis}
        stages: list[ChainStage] = []
        for stage_seg in lis:
            members = [s for s in window if s.stage == stage_seg.stage]
            gids = sorted({g for s in members for g in s.group_ids})
            stages.append(ChainStage(
                stage=stage_seg.stage,
                label=stage_seg.label,
                order=stage_seg.order,
                first_ts=min(s.first_ts for s in members),
                last_ts=max(s.last_ts for s in members),
                count=sum(s.count for s in members),
                group_ids=gids[:100],
                description=self._describe(members, groups_by_id),
            ))
        group_ids = sorted({g for s in window if s.stage in lis_stages for g in s.group_ids})
        scenario_parts: list[str] = []
        for st in stages:
            tactic = SCENARIO_TACTICS.get(st.stage, st.label)
            if tactic not in scenario_parts:
                scenario_parts.append(tactic)
        chain = AttackChain(
            id=len(self.chains) + 1,
            entity_type="host",
            entity=agent or "unknown host",
            stages=stages,
            first_ts=stages[0].first_ts,
            last_ts=max(s.last_ts for s in stages),
            scenario=" → ".join(scenario_parts),
            src_ips=sorted({ip for s in window for ip in s.src_ips})[:20],
            users=sorted({u for s in window for u in s.users})[:20],
            group_ids=group_ids[:500],
            success_after_failures=success_after_fail,
        )
        self.chains.append(chain)
        for gid in chain.group_ids:
            group = groups_by_id.get(gid)
            if group is not None and chain.id not in group.chain_ids:
                group.chain_ids.append(chain.id)

    @staticmethod
    def _describe(members: list[_Segment], groups_by_id: dict[int, AlertGroup]) -> str:
        descriptions: list[str] = []
        for seg in members:
            for gid in sorted(seg.group_ids):
                group = groups_by_id.get(gid)
                if group and group.rule_description not in descriptions:
                    descriptions.append(group.rule_description)
                if len(descriptions) >= 3:
                    break
        return "; ".join(descriptions)

    def _mark_success_pairs(self, groups_by_id: dict[int, AlertGroup]) -> None:
        for success_gid, failure_gids, failures in self.success_pairs:
            group = groups_by_id.get(success_gid)
            if group is not None:
                group.success_after_failures = True
                group.failures_before_success = max(group.failures_before_success, failures)
            for gid in failure_gids:
                fgroup = groups_by_id.get(gid)
                if fgroup is not None:
                    fgroup.success_after_failures = True
                    fgroup.failures_before_success = max(fgroup.failures_before_success, failures)
