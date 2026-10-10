# Результаты автоматических тестов

Среда прогона: Linux x86_64, Python 3.13.16, PySide6 6.12.0, ldap3 2.9.1, openpyxl 3.1.5, Qt offscreen.
Все тесты используют демо-каталог в памяти или mock-соединения ldap3 — изменения в реальном домене не выполняются.

**Итого: 149 тестов, пройдено 149, ошибок 0** (`python -m pytest -q tests`, ~45 с).

| Файл | Что проверяется | Тестов |
|---|---|---|
| `tests/test_adtypes.py` | FILETIME, GeneralizedTime, SID, groupType, декодирование атрибутов и range retrieval | 7 |
| `tests/test_bulk.py` | Массовые операции: CSV, разрешение идентификаторов, план, Dry Run, ошибки по объектам, лимиты, отмена | 10 |
| `tests/test_dn.py` | DN: экранирование RFC 4514, разбор hex/UTF-8, нормализация, вложенность | 17 |
| `tests/test_export_masking.py` | Экспорт CSV/XLSX/HTML, формульные инъекции, маскирование секретов в логах/журнале/БД | 12 |
| `tests/test_filters.py` | LDAP-фильтры: экранирование RFC 4515, попытки инъекции, правила AD 803/804/1941, парсер и сообщения об ошибках | 27 |
| `tests/test_groups_permissions.py` | Группы и права: SID привилегированных групп, вложенность, пустые группы, защита изменений | 12 |
| `tests/test_ldap3_gateway.py` | Шлюз ldap3 (mock-соединение): постраничная выдача, ошибки LDAP/AD, bind-коды, TLS-ошибки, переподключение, read-only, запрет пароля без TLS | 24 |
| `tests/test_ldap3_mock_integration.py` | Шлюз с настоящим ldap3.Connection (MOCK_SYNC): paged search, modify, modify_dn | 3 |
| `tests/test_security_descriptor.py` | DACL: «User cannot change password» | 2 |
| `tests/test_services_misc.py` | Статистика, аудит, отчёты, компьютеры, OU и снимки, пароли, Explorer, журналы событий, сеть, настройки | 16 |
| `tests/test_ui_smoke.py` | GUI (offscreen): все страницы, аудит, поиск, read-only, смена темы | 1 |
| `tests/test_users.py` | Пользователи: отключённые/заблокированные, представления, права, привилегии, сброс пароля, конфликт изменений, создание | 18 |

Дополнительно проверено при подготовке:

* `python main.py --selftest` — OK;
* сборка PyInstaller по `ADAdminToolkit.spec` (onedir) выполнена успешно, собранный бинарник прошёл `--selftest` и запуск GUI в режиме `--demo`
  (проверка выполнялась под Linux; Windows-EXE собирается `build_exe.bat`, где тесты и самопроверка выполняются автоматически);
* `pyflakes adtoolkit` — без замечаний.

## Полный список

```
PASSED  tests/test_adtypes.py::test_filetime_roundtrip
PASSED  tests/test_adtypes.py::test_intervals
PASSED  tests/test_adtypes.py::test_generalized_time
PASSED  tests/test_adtypes.py::test_sid_roundtrip
PASSED  tests/test_adtypes.py::test_group_type
PASSED  tests/test_adtypes.py::test_decode_attributes_types_and_ranges
PASSED  tests/test_adtypes.py::test_uac_text
PASSED  tests/test_bulk.py::test_parse_csv_variants
PASSED  tests/test_bulk.py::test_resolve_identities
PASSED  tests/test_bulk.py::test_plan_shows_changes_skips_and_privileged
PASSED  tests/test_bulk.py::test_dry_run_changes_nothing
PASSED  tests/test_bulk.py::test_read_only_blocks_real_execution
PASSED  tests/test_bulk.py::test_execution_isolates_per_object_errors
PASSED  tests/test_bulk.py::test_privileged_target_group_blocked_until_confirmed
PASSED  tests/test_bulk.py::test_limit_and_move_and_unlock
PASSED  tests/test_bulk.py::test_cancel_stops_batch
PASSED  tests/test_bulk.py::test_prepare_password_reset_never_modifies
PASSED  tests/test_dn.py::test_escape_dn_value[Smith,
PASSED  tests/test_dn.py::test_escape_dn_value[
PASSED  tests/test_dn.py::test_escape_dn_value[trailing
PASSED  tests/test_dn.py::test_escape_dn_value[#hash-\\#hash]
PASSED  tests/test_dn.py::test_escape_dn_value[a+b"c\\d<e>f;g=h-a\\+b\\"c\\\\d\\<e\\>f\\;g\\=h]
PASSED  tests/test_dn.py::test_escape_dn_value[\u0418\u0432\u0430\u043d\u043e\u0432
PASSED  tests/test_dn.py::test_parse_escaped_and_hex
PASSED  tests/test_dn.py::test_utf8_hex_escapes
PASSED  tests/test_dn.py::test_multivalued_rdn_and_build
PASSED  tests/test_dn.py::test_child_dn_escapes_user_input
PASSED  tests/test_dn.py::test_invalid_dns[CN]
PASSED  tests/test_dn.py::test_invalid_dns[=x]
PASSED  tests/test_dn.py::test_invalid_dns[CN=a,]
PASSED  tests/test_dn.py::test_invalid_dns[CN=a\\]
PASSED  tests/test_dn.py::test_invalid_dns[CN=a"b]
PASSED  tests/test_dn.py::test_normalize_and_descendant
PASSED  tests/test_dn.py::test_domain_helpers
PASSED  tests/test_export_masking.py::test_csv_export_metadata_and_injection
PASSED  tests/test_export_masking.py::test_xlsx_export
PASSED  tests/test_export_masking.py::test_html_export_escapes
PASSED  tests/test_export_masking.py::test_safe_cell
PASSED  tests/test_export_masking.py::test_mask_text[bind
PASSED  tests/test_export_masking.py::test_mask_text[{"password":
PASSED  tests/test_export_masking.py::test_mask_text[unicodePwd:
PASSED  tests/test_export_masking.py::test_mask_text[net
PASSED  tests/test_export_masking.py::test_mask_literal_and_mapping
PASSED  tests/test_export_masking.py::test_logging_filter_masks
PASSED  tests/test_export_masking.py::test_errors_never_show_secrets
PASSED  tests/test_export_masking.py::test_journal_and_database_never_store_secrets
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[Parens
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[*-\\2a]
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[C:\\MyFile-C:\\5cMyFile]
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[NUL\x00here-NUL\\00here]
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[Lu\u010di\u0107-Lu\u010di\u0107]
PASSED  tests/test_filters.py::test_escape_rfc4515_vectors[\u0418\u0432\u0430\u043d\u043e\u0432
PASSED  tests/test_filters.py::test_escape_bytes_is_fully_hex_encoded
PASSED  tests/test_filters.py::test_injection_attempt_stays_a_literal_value
PASSED  tests/test_filters.py::test_substring_builders
PASSED  tests/test_filters.py::test_ad_matching_rules
PASSED  tests/test_filters.py::test_predefined_example_filters
PASSED  tests/test_filters.py::test_attribute_names_are_validated
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(cn=a]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(&)]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[cn=a)]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(cn=(a))]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(cn=\\zz)]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(!(cn=a)(cn=b))]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[
PASSED  tests/test_filters.py::test_parser_rejects_invalid[(cn~a)]
PASSED  tests/test_filters.py::test_parser_rejects_invalid[((cn=a))]
PASSED  tests/test_filters.py::test_parser_reports_position
PASSED  tests/test_filters.py::test_parser_roundtrip_and_normalisation
PASSED  tests/test_filters.py::test_parser_depth_limit
PASSED  tests/test_filters.py::test_unescape_utf8_and_binary
PASSED  tests/test_filters.py::test_operators
PASSED  tests/test_groups_permissions.py::test_privileged_groups_detected_by_sid_even_if_renamed
PASSED  tests/test_groups_permissions.py::test_nested_privilege
PASSED  tests/test_groups_permissions.py::test_search_filters_and_marks
PASSED  tests/test_groups_permissions.py::test_transitive_members_and_cycles
PASSED  tests/test_groups_permissions.py::test_empty_groups_consider_primary_group
PASSED  tests/test_groups_permissions.py::test_membership_checks
PASSED  tests/test_groups_permissions.py::test_add_remove_member_with_privileged_guard
PASSED  tests/test_groups_permissions.py::test_group_write_permission_denied
PASSED  tests/test_groups_permissions.py::test_create_group
PASSED  tests/test_groups_permissions.py::test_compare_groups
PASSED  tests/test_groups_permissions.py::test_rights_summary
PASSED  tests/test_groups_permissions.py::test_conflict_on_concurrent_member_change
PASSED  tests/test_ldap3_gateway.py::test_connect_discovers_directory
PASSED  tests/test_ldap3_gateway.py::test_paged_search_follows_cookies
PASSED  tests/test_ldap3_gateway.py::test_base_search_is_not_paged
PASSED  tests/test_ldap3_gateway.py::test_size_limit_marks_truncated
PASSED  tests/test_ldap3_gateway.py::test_search_filter_string_is_validated_before_sending
PASSED  tests/test_ldap3_gateway.py::test_search_errors_mapped[result0-PermissionDeniedError]
PASSED  tests/test_ldap3_gateway.py::test_search_errors_mapped[result1-ObjectNotFoundError]
PASSED  tests/test_ldap3_gateway.py::test_search_errors_mapped[result2-ToolkitError]
PASSED  tests/test_ldap3_gateway.py::test_search_errors_mapped[result3-LdapTimeoutError]
PASSED  tests/test_ldap3_gateway.py::test_bind_errors_mapped[52e-\u041d\u0435\u0432\u0435\u0440\u043d\u043e\u0435
PASSED  tests/test_ldap3_gateway.py::test_bind_errors_mapped[775-\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u0430]
PASSED  tests/test_ldap3_gateway.py::test_bind_errors_mapped[532-\u043f\u0430\u0440\u043e\u043b\u044f
PASSED  tests/test_ldap3_gateway.py::test_bind_errors_mapped[533-\u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0430]
PASSED  tests/test_ldap3_gateway.py::test_bind_errors_mapped[701-\u0443\u0447\u0451\u0442\u043d\u043e\u0439
PASSED  tests/test_ldap3_gateway.py::test_stronger_auth_required
PASSED  tests/test_ldap3_gateway.py::test_password_never_sent_over_plain_ldap
PASSED  tests/test_ldap3_gateway.py::test_plain_kerberos_requires_explicit_opt_in
PASSED  tests/test_ldap3_gateway.py::test_connection_errors_mapped
PASSED  tests/test_ldap3_gateway.py::test_read_is_retried_after_reconnect
PASSED  tests/test_ldap3_gateway.py::test_write_is_not_retried_after_connection_loss
PASSED  tests/test_ldap3_gateway.py::test_read_only_blocks_writes_before_network
PASSED  tests/test_ldap3_gateway.py::test_no_such_attribute_maps_to_conflict
PASSED  tests/test_ldap3_gateway.py::test_unicodepwd_cannot_be_written_via_modify
PASSED  tests/test_ldap3_gateway.py::test_password_policy_error_mapped_and_masked
PASSED  tests/test_ldap3_mock_integration.py::test_connect_and_paged_search
PASSED  tests/test_ldap3_mock_integration.py::test_modify_with_optimistic_concurrency
PASSED  tests/test_ldap3_mock_integration.py::test_move_and_errors
PASSED  tests/test_security_descriptor.py::test_cannot_change_password_detected
PASSED  tests/test_security_descriptor.py::test_allow_only_dacl
PASSED  tests/test_services_misc.py::test_dashboard_exact_counts
PASSED  tests/test_services_misc.py::test_dashboard_reports_errors
PASSED  tests/test_services_misc.py::test_audit_runs_all_checks
PASSED  tests/test_services_misc.py::test_reports_have_metadata
PASSED  tests/test_services_misc.py::test_computers
PASSED  tests/test_services_misc.py::test_ou_service
PASSED  tests/test_services_misc.py::test_password_generation_and_policy
PASSED  tests/test_services_misc.py::test_explorer_read_only_and_builder
PASSED  tests/test_services_misc.py::test_compare_users
PASSED  tests/test_services_misc.py::test_offboarding_plan_and_execute
PASSED  tests/test_services_misc.py::test_events_parsing_and_xpath
PASSED  tests/test_services_misc.py::test_events_query_with_fake_runner
PASSED  tests/test_services_misc.py::test_events_unavailable_is_reported_not_simulated
PASSED  tests/test_services_misc.py::test_network_checks_real_and_validated
PASSED  tests/test_services_misc.py::test_settings_layering
PASSED  tests/test_services_misc.py::test_example_config_is_valid
PASSED  tests/test_ui_smoke.py::test_main_window_demo
PASSED  tests/test_users.py::test_disabled_and_locked_views
PASSED  tests/test_users.py::test_views_return_consistent_results
PASSED  tests/test_users.py::test_text_search_with_special_characters_is_safe
PASSED  tests/test_users.py::test_enable_disable_with_journal
PASSED  tests/test_users.py::test_privileged_account_requires_confirmation
PASSED  tests/test_users.py::test_krbtgt_protected
PASSED  tests/test_users.py::test_unlock
PASSED  tests/test_users.py::test_reset_password_policy_and_encryption
PASSED  tests/test_users.py::test_read_only_mode
PASSED  tests/test_users.py::test_permission_precheck
PASSED  tests/test_users.py::test_optimistic_concurrency_conflict
PASSED  tests/test_users.py::test_update_attributes_validation
PASSED  tests/test_users.py::test_account_expiry
PASSED  tests/test_users.py::test_move_validation
PASSED  tests/test_users.py::test_create_user_and_conflicts
PASSED  tests/test_users.py::test_create_user_privileged_group_needs_confirmation
PASSED  tests/test_users.py::test_copy_from_user_excludes_privileged_groups
PASSED  tests/test_users.py::test_group_paths_and_precise_logon
```
