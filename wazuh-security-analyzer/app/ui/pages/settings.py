"""Settings: analysis mode, AI provider, API keys, threat intelligence, network, risk model, privacy."""

from __future__ import annotations

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.ai.engine import EXTERNAL_WARNING
from app.ai.providers.factory import PROVIDER_LABELS, create_provider
from app.core.config import AppConfig, AssetRule
from app.core.errors import ProviderResponseError, ProviderUnavailableError
from app.core.secrets import KNOWN_SECRETS
from app.ui import workers
from app.ui.pages.base import BasePage


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    widget.setObjectName("page")
    widget.setAttribute(Qt.WA_StyledBackground, True)
    area.setWidget(widget)
    return area


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()]


class SettingsPage(BasePage):
    title = "Settings"
    subtitle = "Configuration is stored in config.yaml in your profile. API keys are stored in Windows Credential Manager."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self._build_general()
        self._build_ai()
        self._build_keys()
        self._build_ti()
        self._build_network()
        self._build_risk()
        self._build_assets()
        self._build_privacy()
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reset = QPushButton("Revert")
        reset.clicked.connect(self.load)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        buttons.addWidget(reset)
        buttons.addWidget(save)
        self.root.addLayout(buttons)
        self.load()

    # ------------------------------------------------------------------ builders
    def _build_general(self) -> None:
        w = QWidget()
        form = QFormLayout(w)
        self.mode_offline = QRadioButton("OFFLINE - local analysis only (no network access)")
        self.mode_online = QRadioButton("ONLINE - CVE lookup, IOC reputation, CISA KEV")
        grp = QButtonGroup(w)
        grp.addButton(self.mode_offline)
        grp.addButton(self.mode_online)
        form.addRow("Analysis mode", self.mode_offline)
        form.addRow("", self.mode_online)
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        form.addRow("Log level", self.log_level)
        self.page_size = QSpinBox()
        self.page_size.setRange(50, 5000)
        form.addRow("Table page size", self.page_size)
        self.store_raw = QCheckBox("Store raw events for the technical view (compressed)")
        form.addRow("Storage", self.store_raw)
        self.dedup = QCheckBox("Remove duplicate alerts (same alert ID loaded twice)")
        form.addRow("", self.dedup)
        self.keep_ws = QSpinBox()
        self.keep_ws.setRange(1, 100)
        form.addRow("Keep last N analyses", self.keep_ws)
        self.max_file = QSpinBox()
        self.max_file.setRange(1, 1_000_000)
        self.max_file.setSuffix(" MB")
        form.addRow("Max file size", self.max_file)
        self.max_archive = QSpinBox()
        self.max_archive.setRange(1, 1_000_000)
        self.max_archive.setSuffix(" MB")
        form.addRow("Max decompressed archive size", self.max_archive)
        self.max_ratio = QSpinBox()
        self.max_ratio.setRange(2, 10_000)
        form.addRow("Max compression ratio", self.max_ratio)
        self.tabs.addTab(_scroll(w), "General")

    def _build_ai(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        warn = QLabel(EXTERNAL_WARNING)
        warn.setObjectName("warning")
        warn.setWordWrap(True)
        lay.addWidget(warn)
        form = QFormLayout()
        self.ai_provider = QComboBox()
        for key, lbl in PROVIDER_LABELS.items():
            self.ai_provider.addItem(lbl, key)
        form.addRow("AI provider", self.ai_provider)
        self.openai_model = QLineEdit()
        form.addRow("OpenAI model", self.openai_model)
        self.anthropic_model = QLineEdit()
        form.addRow("Anthropic model", self.anthropic_model)
        self.ollama_url = QLineEdit()
        form.addRow("Ollama URL", self.ollama_url)
        model_row = QHBoxLayout()
        self.ollama_model = QComboBox()
        self.ollama_model.setEditable(True)
        refresh = QPushButton("List installed models")
        refresh.clicked.connect(self._list_ollama)
        model_row.addWidget(self.ollama_model, 1)
        model_row.addWidget(refresh)
        form.addRow("Ollama model (qwen, llama, mistral…)", model_row)
        self.compat_url = QLineEdit()
        form.addRow("OpenAI-compatible base URL", self.compat_url)
        self.compat_model = QLineEdit()
        form.addRow("OpenAI-compatible model", self.compat_model)
        self.ai_timeout = QSpinBox()
        self.ai_timeout.setRange(5, 900)
        self.ai_timeout.setSuffix(" s")
        form.addRow("Timeout", self.ai_timeout)
        self.ai_temperature = QDoubleSpinBox()
        self.ai_temperature.setRange(0, 1)
        self.ai_temperature.setSingleStep(0.05)
        form.addRow("Temperature", self.ai_temperature)
        self.ai_tokens = QSpinBox()
        self.ai_tokens.setRange(256, 16000)
        form.addRow("Max output tokens", self.ai_tokens)
        self.ai_related = QSpinBox()
        self.ai_related.setRange(1, 200)
        form.addRow("Related alerts in context", self.ai_related)
        self.anon_local = QCheckBox("Anonymize data also for local AI (Ollama / localhost endpoints)")
        form.addRow("Privacy", self.anon_local)
        form.addRow("", QLabel("Data sent to cloud providers (OpenAI, Anthropic) is always anonymized."))
        lay.addLayout(form)
        test_row = QHBoxLayout()
        self.ai_test_btn = QPushButton("Test connection")
        self.ai_test_btn.clicked.connect(self._test_ai)
        self.ai_test_result = QLabel("")
        self.ai_test_result.setWordWrap(True)
        test_row.addWidget(self.ai_test_btn)
        test_row.addWidget(self.ai_test_result, 1)
        lay.addLayout(test_row)
        lay.addStretch(1)
        self.tabs.addTab(_scroll(w), "AI provider")

    def _build_keys(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        backend = ("Windows Credential Manager / OS keychain" if self.ctx.secrets.persistent
                   else "memory only (no secure OS credential store available - keys are lost on exit)")
        info = QLabel(f"Secrets are stored in: <b>{backend}</b>. They are never written to config files or logs.")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.key_edits: dict[str, QLineEdit] = {}
        self.key_status: dict[str, QLabel] = {}
        for name, lbl in KNOWN_SECRETS.items():
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText("not set")
            status = QLabel("")
            status.setObjectName("muted")
            save = QPushButton("Save")
            clear = QPushButton("Clear")
            save.clicked.connect(lambda _c=False, n=name: self._save_key(n))
            clear.clicked.connect(lambda _c=False, n=name: self._clear_key(n))
            row.addWidget(edit, 1)
            row.addWidget(save)
            row.addWidget(clear)
            row.addWidget(status)
            self.key_edits[name] = edit
            self.key_status[name] = status
            form.addRow(lbl, row)
        lay.addLayout(form)
        lay.addStretch(1)
        self.tabs.addTab(_scroll(w), "API keys")

    def _build_ti(self) -> None:
        w = QWidget()
        form = QFormLayout(w)
        self.vt = QCheckBox("VirusTotal (IP, domain, URL, file hash)")
        self.abuse = QCheckBox("AbuseIPDB (IP reputation, country, ISP)")
        self.otx = QCheckBox("AlienVault OTX (pulses)")
        self.nvd = QCheckBox("NVD - CVE details, CVSS, CWE, affected software")
        self.kev = QCheckBox("CISA Known Exploited Vulnerabilities catalog")
        self.active_dns = QCheckBox("Active domain checks (DNS resolution + TLS certificate) - contacts the domain")
        for cb in (self.vt, self.abuse, self.otx, self.nvd, self.kev, self.active_dns):
            form.addRow("", cb)
        self.max_ioc = QSpinBox()
        self.max_ioc.setRange(0, 5000)
        form.addRow("Max IOC lookups per analysis", self.max_ioc)
        self.max_cve = QSpinBox()
        self.max_cve.setRange(0, 2000)
        form.addRow("Max NVD lookups per analysis", self.max_cve)
        self.ti_ttl = QSpinBox()
        self.ti_ttl.setRange(0, 24 * 90)
        self.ti_ttl.setSuffix(" h")
        form.addRow("Cache lifetime", self.ti_ttl)
        self.ti_conc = QSpinBox()
        self.ti_conc.setRange(1, 32)
        form.addRow("Parallel requests", self.ti_conc)
        form.addRow("", QLabel("Only public indicators are sent. Internal IPs, usernames and hostnames never leave "
                               "this computer."))
        self.tabs.addTab(_scroll(w), "Threat intelligence")

    def _build_network(self) -> None:
        w = QWidget()
        form = QFormLayout(w)
        self.proxy = QLineEdit()
        self.proxy.setPlaceholderText("http://proxy.example:8080 (empty = direct)")
        form.addRow("Proxy", self.proxy)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 300)
        self.timeout.setSuffix(" s")
        form.addRow("Request timeout", self.timeout)
        self.verify_tls = QCheckBox("Verify TLS certificates (strongly recommended)")
        form.addRow("TLS", self.verify_tls)
        self.ca_bundle = QLineEdit()
        self.ca_bundle.setPlaceholderText("Path to corporate CA bundle (PEM) for TLS inspection proxies")
        form.addRow("CA bundle", self.ca_bundle)
        self.max_resp = QSpinBox()
        self.max_resp.setRange(1, 200)
        self.max_resp.setSuffix(" MB")
        form.addRow("Max API response size", self.max_resp)
        self.tabs.addTab(_scroll(w), "Network")

    def _build_risk(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.thresholds: dict[str, QSpinBox] = {}
        for key in ("critical", "high", "medium", "low"):
            sb = QSpinBox()
            sb.setRange(0, 100)
            self.thresholds[key] = sb
            form.addRow(f"{key.capitalize()} ≥", sb)
        self.bf_threshold = QSpinBox()
        self.bf_threshold.setRange(2, 10000)
        form.addRow("Brute-force threshold (failures per window)", self.bf_threshold)
        self.window = QSpinBox()
        self.window.setRange(1, 10080)
        self.window.setSuffix(" min")
        form.addRow("Correlation window", self.window)
        self.min_stages = QSpinBox()
        self.min_stages.setRange(2, 8)
        form.addRow("Minimum attack-chain stages", self.min_stages)
        lay.addLayout(form)
        lay.addWidget(QLabel("Risk weights (YAML) - points contributed by each factor:"))
        self.weights_edit = QPlainTextEdit()
        self.weights_edit.setMinimumHeight(260)
        lay.addWidget(self.weights_edit, 1)
        self.tabs.addTab(_scroll(w), "Risk model")

    def _build_assets(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Asset criticality rules (YAML list, first match wins; glob patterns on agent name):"))
        self.assets_edit = QPlainTextEdit()
        self.assets_edit.setMinimumHeight(180)
        lay.addWidget(self.assets_edit)
        form = QFormLayout()
        self.default_crit = QComboBox()
        self.default_crit.addItems(["low", "medium", "high", "critical"])
        form.addRow("Default criticality", self.default_crit)
        self.internal_nets = QPlainTextEdit()
        self.internal_nets.setPlaceholderText("Additional internal networks, one CIDR per line")
        self.internal_nets.setMaximumHeight(90)
        form.addRow("Internal networks", self.internal_nets)
        self.scanners = QPlainTextEdit()
        self.scanners.setPlaceholderText("Authorised scanners (IP or CIDR), one per line")
        self.scanners.setMaximumHeight(90)
        form.addRow("Known scanners", self.scanners)
        self.dashboard_url = QLineEdit()
        form.addRow("Wazuh dashboard URL", self.dashboard_url)
        lay.addLayout(form)
        self.tabs.addTab(_scroll(w), "Assets && Wazuh")

    def _build_privacy(self) -> None:
        w = QWidget()
        form = QFormLayout(w)
        self.mask: dict[str, QCheckBox] = {}
        for key, lbl in (("mask_usernames", "Mask usernames"), ("mask_emails", "Mask e-mail addresses"),
                         ("mask_internal_ips", "Mask internal IP addresses"),
                         ("mask_external_ips", "Mask external IP addresses (hides the IOC from the AI)"),
                         ("mask_hostnames", "Mask hostnames"), ("mask_domains", "Mask internal domains"),
                         ("mask_personal_data", "Mask phone and card numbers")):
            cb = QCheckBox(lbl)
            self.mask[key] = cb
            form.addRow("", cb)
        form.addRow("", QLabel("Passwords, tokens, cookies, API keys and private keys are always removed."))
        self.internal_domains = QPlainTextEdit()
        self.internal_domains.setPlaceholderText("corp.example\ncompany.uz")
        self.internal_domains.setMaximumHeight(100)
        form.addRow("Internal domains", self.internal_domains)
        self.tabs.addTab(_scroll(w), "Privacy")

    # ------------------------------------------------------------------ load / save
    def load(self) -> None:
        c = self.ctx.config
        (self.mode_online if c.network.online else self.mode_offline).setChecked(True)
        self.log_level.setCurrentText(c.logging.level)
        self.page_size.setValue(c.ui.page_size)
        self.store_raw.setChecked(c.storage.store_raw_events)
        self.dedup.setChecked(c.storage.deduplicate)
        self.keep_ws.setValue(c.storage.keep_workspaces)
        self.max_file.setValue(c.limits.max_file_size_mb)
        self.max_archive.setValue(c.limits.max_archive_total_mb)
        self.max_ratio.setValue(c.limits.max_compression_ratio)
        self.ai_provider.setCurrentIndex(max(0, self.ai_provider.findData(c.ai.provider)))
        self.openai_model.setText(c.ai.openai_model)
        self.anthropic_model.setText(c.ai.anthropic_model)
        self.ollama_url.setText(c.ai.ollama_url)
        self.ollama_model.setCurrentText(c.ai.ollama_model)
        self.compat_url.setText(c.ai.compatible_base_url)
        self.compat_model.setText(c.ai.compatible_model)
        self.ai_timeout.setValue(c.ai.timeout_seconds)
        self.ai_temperature.setValue(c.ai.temperature)
        self.ai_tokens.setValue(c.ai.max_tokens)
        self.ai_related.setValue(c.ai.max_related_events)
        self.anon_local.setChecked(c.ai.anonymize_local)
        for name, edit in self.key_edits.items():
            edit.clear()
            self.key_status[name].setText("✔ stored" if self.ctx.secrets.has(name) else "not set")
        ti = c.threat_intel
        self.vt.setChecked(ti.virustotal_enabled)
        self.abuse.setChecked(ti.abuseipdb_enabled)
        self.otx.setChecked(ti.otx_enabled)
        self.nvd.setChecked(ti.nvd_enabled)
        self.kev.setChecked(ti.cisa_kev_enabled)
        self.active_dns.setChecked(ti.active_domain_checks)
        self.max_ioc.setValue(ti.max_ioc_lookups)
        self.max_cve.setValue(ti.max_cve_lookups)
        self.ti_ttl.setValue(ti.cache_ttl_hours)
        self.ti_conc.setValue(ti.concurrency)
        n = c.network
        self.proxy.setText(n.proxy)
        self.timeout.setValue(n.timeout_seconds)
        self.verify_tls.setChecked(n.verify_tls)
        self.ca_bundle.setText(n.ca_bundle)
        self.max_resp.setValue(n.max_response_mb)
        for key, sb in self.thresholds.items():
            sb.setValue(getattr(c.risk_thresholds, key))
        self.bf_threshold.setValue(c.correlation.bruteforce_threshold)
        self.window.setValue(c.correlation.chain_window_minutes)
        self.min_stages.setValue(c.correlation.min_chain_stages)
        self.weights_edit.setPlainText(yaml.safe_dump(c.risk_weights.model_dump(), sort_keys=False))
        self.assets_edit.setPlainText(yaml.safe_dump([a.model_dump() for a in c.wazuh.asset_criticality],
                                                     sort_keys=False))
        self.default_crit.setCurrentText(c.wazuh.default_asset_criticality)
        self.internal_nets.setPlainText("\n".join(c.wazuh.internal_networks))
        self.scanners.setPlainText("\n".join(c.wazuh.known_scanners))
        self.dashboard_url.setText(c.wazuh.dashboard_url)
        for key, cb in self.mask.items():
            cb.setChecked(getattr(c.privacy, key))
        self.internal_domains.setPlainText("\n".join(c.privacy.internal_domains))

    def build_config(self) -> AppConfig:
        data = self.ctx.config.model_dump()
        data["network"].update(mode="online" if self.mode_online.isChecked() else "offline",
                               proxy=self.proxy.text().strip(), timeout_seconds=self.timeout.value(),
                               verify_tls=self.verify_tls.isChecked(), ca_bundle=self.ca_bundle.text().strip(),
                               max_response_mb=self.max_resp.value())
        data["logging"]["level"] = self.log_level.currentText()
        data["ui"]["page_size"] = self.page_size.value()
        data["storage"].update(store_raw_events=self.store_raw.isChecked(), deduplicate=self.dedup.isChecked(),
                               keep_workspaces=self.keep_ws.value())
        data["limits"].update(max_file_size_mb=self.max_file.value(), max_archive_total_mb=self.max_archive.value(),
                              max_compression_ratio=self.max_ratio.value())
        data["ai"].update(provider=self.ai_provider.currentData(), openai_model=self.openai_model.text().strip(),
                          anthropic_model=self.anthropic_model.text().strip(),
                          ollama_url=self.ollama_url.text().strip(), ollama_model=self.ollama_model.currentText().strip(),
                          compatible_base_url=self.compat_url.text().strip(),
                          compatible_model=self.compat_model.text().strip(), timeout_seconds=self.ai_timeout.value(),
                          temperature=self.ai_temperature.value(), max_tokens=self.ai_tokens.value(),
                          max_related_events=self.ai_related.value(), anonymize_local=self.anon_local.isChecked())
        data["threat_intel"].update(virustotal_enabled=self.vt.isChecked(), abuseipdb_enabled=self.abuse.isChecked(),
                                    otx_enabled=self.otx.isChecked(), nvd_enabled=self.nvd.isChecked(),
                                    cisa_kev_enabled=self.kev.isChecked(),
                                    active_domain_checks=self.active_dns.isChecked(),
                                    max_ioc_lookups=self.max_ioc.value(), max_cve_lookups=self.max_cve.value(),
                                    cache_ttl_hours=self.ti_ttl.value(), concurrency=self.ti_conc.value())
        data["risk_thresholds"] = {k: sb.value() for k, sb in self.thresholds.items()}
        data["correlation"].update(bruteforce_threshold=self.bf_threshold.value(),
                                   chain_window_minutes=self.window.value(), min_chain_stages=self.min_stages.value())
        weights = yaml.safe_load(self.weights_edit.toPlainText() or "{}")
        if not isinstance(weights, dict):
            raise ValueError("Risk weights must be a YAML mapping")
        data["risk_weights"] = weights
        assets = yaml.safe_load(self.assets_edit.toPlainText() or "[]") or []
        if not isinstance(assets, list):
            raise ValueError("Asset rules must be a YAML list")
        data["wazuh"].update(asset_criticality=[AssetRule.model_validate(a).model_dump() for a in assets],
                             default_asset_criticality=self.default_crit.currentText(),
                             internal_networks=_lines(self.internal_nets.toPlainText()),
                             known_scanners=_lines(self.scanners.toPlainText()),
                             dashboard_url=self.dashboard_url.text().strip())
        data["privacy"].update({k: cb.isChecked() for k, cb in self.mask.items()})
        data["privacy"]["internal_domains"] = _lines(self.internal_domains.toPlainText())
        return AppConfig.model_validate(data)

    def save(self) -> None:
        try:
            config = self.build_config()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid settings", f"The settings were not saved:\n\n{exc}")
            return
        if config.ai.provider in ("openai", "anthropic") and self.ctx.config.ai.provider not in ("openai", "anthropic"):
            if QMessageBox.warning(self, "External AI provider", EXTERNAL_WARNING + "\n\nEnable it anyway?",
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        self.ctx.update_config(config)
        self.ctx.statusMessage.emit("Settings saved. Changes to the risk model apply to the next analysis.")

    # ------------------------------------------------------------------ actions
    def _save_key(self, name: str) -> None:
        value = self.key_edits[name].text().strip()
        if not value:
            return
        persistent = self.ctx.secrets.set(name, value)
        self.key_edits[name].clear()
        self.key_status[name].setText("✔ stored" if persistent else "✔ memory only")

    def _clear_key(self, name: str) -> None:
        self.ctx.secrets.delete(name)
        self.key_status[name].setText("not set")

    def _test_ai(self) -> None:
        try:
            config = self.build_config()
        except Exception as exc:
            self.ai_test_result.setText(f"Invalid settings: {exc}")
            return
        provider = create_provider(config, self.ctx.secrets)
        if provider is None:
            self.ai_test_result.setText("AI is disabled.")
            return
        self.ai_test_btn.setEnabled(False)
        self.ai_test_result.setText("Testing…")

        def job(progress, cancel):
            try:
                return provider.test_connection()
            except (ProviderUnavailableError, ProviderResponseError) as exc:
                return f"✖ {exc}"

        def done(text: str) -> None:
            self.ai_test_btn.setEnabled(True)
            self.ai_test_result.setText(text)

        task = workers.Task(job)
        task.signals.finished.connect(done)
        task.signals.failed.connect(done)
        workers.start(task)

    def _list_ollama(self) -> None:
        try:
            config = self.build_config()
        except Exception:
            return
        config.ai.provider = "ollama"
        provider = create_provider(config, self.ctx.secrets)

        def job(progress, cancel):
            try:
                return provider.list_models()
            except (ProviderUnavailableError, ProviderResponseError) as exc:
                return str(exc)

        def done(result) -> None:
            if isinstance(result, list):
                current = self.ollama_model.currentText()
                self.ollama_model.clear()
                self.ollama_model.addItems(result or [current])
                self.ollama_model.setCurrentText(current if current in result or not result else result[0])
                self.ai_test_result.setText(f"{len(result)} model(s) installed in Ollama")
            else:
                self.ai_test_result.setText(f"✖ {result}")

        task = workers.Task(job)
        task.signals.finished.connect(done)
        workers.start(task)
