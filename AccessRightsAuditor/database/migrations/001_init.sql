-- Access Rights Auditor (ARA) — начальная схема БД.
-- Первичные ключи — UUID; каскадное удаление исторических записей запрещено (ON DELETE RESTRICT по умолчанию).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ===================== RBAC приложения =====================
CREATE TABLE users (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username              text NOT NULL UNIQUE,
  password_hash         text NOT NULL,
  full_name             text NOT NULL,
  is_active             boolean NOT NULL DEFAULT true,
  must_change_password  boolean NOT NULL DEFAULT true,
  failed_attempts       integer NOT NULL DEFAULT 0,
  locked_until          timestamptz,
  last_login_at         timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_roles (
  id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code  text NOT NULL UNIQUE,
  name  text NOT NULL
);

CREATE TABLE app_role_permissions (
  role_id          uuid NOT NULL REFERENCES app_roles(id),
  permission_code  text NOT NULL,
  PRIMARY KEY (role_id, permission_code)
);

CREATE TABLE user_role_assignments (
  user_id  uuid NOT NULL REFERENCES users(id),
  role_id  uuid NOT NULL REFERENCES app_roles(id),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE sessions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash    text NOT NULL UNIQUE,
  user_id       uuid NOT NULL REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,
  ip            text,
  user_agent    text,
  revoked_at    timestamptz
);

CREATE TABLE app_settings (
  key         text PRIMARY KEY,
  value       jsonb NOT NULL,
  updated_by  uuid REFERENCES users(id),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ===================== Справочники =====================
CREATE TABLE departments (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code       text NOT NULL UNIQUE,
  name       text NOT NULL,
  parent_id  uuid REFERENCES departments(id),
  is_active  boolean NOT NULL DEFAULT true
);

CREATE TABLE positions (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code       text NOT NULL UNIQUE,
  name       text NOT NULL,
  is_active  boolean NOT NULL DEFAULT true
);

CREATE TABLE employees (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_key            text NOT NULL,
  hr_source               text NOT NULL DEFAULT 'HR',
  full_name               text NOT NULL,
  department_id           uuid REFERENCES departments(id),
  position_id             uuid REFERENCES positions(id),
  employment_status       text NOT NULL DEFAULT 'ACTIVE'
                          CHECK (employment_status IN ('ACTIVE','TERMINATED','LEAVE','TRANSFERRED')),
  valid_from              date,            -- дата приёма
  valid_to                date,            -- дата увольнения (если применимо)
  previous_department_id  uuid REFERENCES departments(id),
  previous_position_id    uuid REFERENCES positions(id),
  transferred_at          date,
  updated_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (hr_source, employee_key)
);

CREATE TABLE systems (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL UNIQUE,
  name           text NOT NULL,
  description    text,
  owner_user_id  uuid REFERENCES users(id),
  is_active      boolean NOT NULL DEFAULT true
);

CREATE TABLE access_roles (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  system_id    uuid NOT NULL REFERENCES systems(id),
  role_code    text NOT NULL,
  role_name    text NOT NULL,
  description  text,
  UNIQUE (system_id, role_code)
);

CREATE TABLE modules (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  system_id  uuid NOT NULL REFERENCES systems(id),
  code       text NOT NULL,
  name       text NOT NULL,
  UNIQUE (system_id, code)
);

CREATE TABLE operations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  system_id   uuid NOT NULL REFERENCES systems(id),
  module_id   uuid NOT NULL REFERENCES modules(id),
  code        text NOT NULL,
  name        text NOT NULL,
  risk_level  text NOT NULL DEFAULT 'MEDIUM' CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  UNIQUE (module_id, code)
);

-- Состав (профиль) роли: в какие атомарные операции разворачивается роль.
CREATE TABLE role_operations (
  role_id       uuid NOT NULL REFERENCES access_roles(id),
  operation_id  uuid NOT NULL REFERENCES operations(id),
  PRIMARY KEY (role_id, operation_id)
);

-- Таблица алиасов (нормализация разных написаний).
CREATE TABLE aliases (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type  text NOT NULL CHECK (entity_type IN ('SYSTEM','ROLE','MODULE','OPERATION','EMPLOYEE')),
  system_id    uuid REFERENCES systems(id),
  alias        text NOT NULL,
  target_id    uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX aliases_uq ON aliases (entity_type, COALESCE(system_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(alias));

-- ===================== Матрица полномочий =====================
CREATE TABLE matrix_versions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version      text NOT NULL UNIQUE,
  name         text NOT NULL,
  description  text,
  valid_from   date NOT NULL,
  valid_to     date,
  status       text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','APPROVED','ARCHIVED')),
  checksum     text,
  created_by   uuid REFERENCES users(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  approved_by  uuid REFERENCES users(id),
  approved_at  timestamptz
);

CREATE TABLE matrix_rules (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id     uuid NOT NULL REFERENCES matrix_versions(id),
  system_id      uuid NOT NULL REFERENCES systems(id),
  department_id  uuid REFERENCES departments(id),  -- NULL = любое подразделение
  position_id    uuid REFERENCES positions(id),    -- NULL = любая должность
  role_id        uuid REFERENCES access_roles(id), -- NULL = любая роль системы
  module_id      uuid REFERENCES modules(id),      -- NULL = весь состав роли
  operation_id   uuid REFERENCES operations(id),   -- NULL = все операции модуля/роли
  effect         text NOT NULL DEFAULT 'ALLOW' CHECK (effect IN ('ALLOW','DENY')),
  severity       text CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  source_ref     text NOT NULL,
  owner          text NOT NULL,
  valid_from     date NOT NULL,
  valid_to       date,
  status         text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
  notes          text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX matrix_rules_version_idx ON matrix_rules (version_id, system_id);

-- ===================== SoD =====================
CREATE TABLE sod_rules (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code                       text NOT NULL UNIQUE,
  name                       text NOT NULL,
  severity                   text NOT NULL DEFAULT 'HIGH' CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  scope                      text NOT NULL DEFAULT 'EMPLOYEE' CHECK (scope IN ('EMPLOYEE','EMPLOYEE_SYSTEM')),
  justification              text NOT NULL,
  process                    text,
  valid_from                 date NOT NULL,
  valid_to                   date,
  status                     text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
  compensating_control       text,
  compensating_approved_by   text,
  compensating_approved_at   date,
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sod_rule_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id       uuid NOT NULL REFERENCES sod_rules(id),
  side          integer NOT NULL CHECK (side >= 1),
  item_type     text NOT NULL CHECK (item_type IN ('OPERATION','ROLE')),
  operation_id  uuid REFERENCES operations(id),
  role_id       uuid REFERENCES access_roles(id),
  CHECK ((item_type = 'OPERATION' AND operation_id IS NOT NULL) OR (item_type = 'ROLE' AND role_id IS NOT NULL))
);

-- ===================== Исключения =====================
CREATE TABLE exceptions (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id           uuid NOT NULL REFERENCES employees(id),
  system_id             uuid NOT NULL REFERENCES systems(id),
  role_id               uuid REFERENCES access_roles(id),
  operation_id          uuid REFERENCES operations(id),
  ticket_ref            text NOT NULL,
  author                text NOT NULL,
  approved_by           text NOT NULL,
  reason                text NOT NULL,
  valid_from            date NOT NULL,
  valid_to              date NOT NULL,
  compensating_control  text NOT NULL,
  status                text NOT NULL DEFAULT 'APPROVED' CHECK (status IN ('DRAFT','APPROVED','REVOKED')),
  created_by            uuid REFERENCES users(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

-- ===================== Аудиты и импорт =====================
CREATE TABLE audit_runs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name               text NOT NULL,
  description        text,
  as_of_date         date NOT NULL,
  matrix_version_id  uuid REFERENCES matrix_versions(id),
  status             text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','RUNNING','COMPLETED','FAILED')),
  created_by         uuid REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  started_by         uuid REFERENCES users(id),
  started_at         timestamptz,
  completed_at       timestamptz,
  rules_snapshot     jsonb,     -- зафиксированные SoD-правила, политика критичности, исключения
  rules_checksum     text,
  matrix_checksum    text,
  package_checksum   text,      -- SHA-256 по контрольным суммам всех файлов пакета
  result_checksum    text,      -- SHA-256 канонического набора результатов
  summary            jsonb,
  error_text         text
);

CREATE TABLE import_mapping_templates (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL UNIQUE,
  mapping     jsonb NOT NULL,
  created_by  uuid REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE import_batches (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id       uuid NOT NULL REFERENCES audit_runs(id),
  file_name      text NOT NULL,
  stored_path    text NOT NULL,
  file_size      bigint NOT NULL,
  file_type      text NOT NULL,
  sha256         text NOT NULL,
  uploaded_by    uuid REFERENCES users(id),
  uploaded_at    timestamptz NOT NULL DEFAULT now(),
  mapping_json   jsonb,
  sheet_name     text,
  status         text NOT NULL DEFAULT 'UPLOADED' CHECK (status IN ('UPLOADED','PROCESSED','PROCESSED_WITH_ERRORS','FAILED')),
  total_rows     integer NOT NULL DEFAULT 0,
  ok_rows        integer NOT NULL DEFAULT 0,
  error_rows     integer NOT NULL DEFAULT 0,
  warning_rows   integer NOT NULL DEFAULT 0,
  processed_at   timestamptz,
  file_warnings  jsonb
);

CREATE TABLE import_rows (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id           uuid NOT NULL REFERENCES import_batches(id),
  sheet_name         text,
  row_number         integer NOT NULL,
  raw_json           jsonb NOT NULL,
  normalized_status  text NOT NULL CHECK (normalized_status IN ('OK','WARNING','ERROR','DUPLICATE')),
  error_text         text,
  error_column       text
);
CREATE INDEX import_rows_batch_idx ON import_rows (batch_id, normalized_status);

CREATE TABLE access_snapshots (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id           uuid NOT NULL REFERENCES audit_runs(id),
  batch_id           uuid NOT NULL REFERENCES import_batches(id),
  source_row_id      uuid NOT NULL REFERENCES import_rows(id),
  employee_id        uuid REFERENCES employees(id),
  system_id          uuid REFERENCES systems(id),
  role_id            uuid REFERENCES access_roles(id),
  module_id          uuid REFERENCES modules(id),
  operation_id       uuid REFERENCES operations(id),
  employee_key_raw   text,
  full_name_raw      text,
  login              text NOT NULL DEFAULT '',
  system_raw         text,
  role_raw           text,
  module_raw         text,
  operation_raw      text,
  assigned_at        date,
  expanded_from_role boolean NOT NULL DEFAULT false,
  normalized_status  text NOT NULL DEFAULT 'OK' CHECK (normalized_status IN ('OK','NEEDS_REVIEW')),
  review_reason      text,
  result_status      text CHECK (result_status IN ('COMPLIANT','VIOLATION','COVERED_BY_EXCEPTION','NEEDS_REVIEW')),
  access_key         text NOT NULL
);
-- Уникальность атомарного назначения в рамках аудита (NULL учитывается через COALESCE).
CREATE UNIQUE INDEX access_snapshots_uq ON access_snapshots (
  audit_id, access_key
);
CREATE INDEX access_snapshots_audit_idx ON access_snapshots (audit_id, employee_id);

CREATE TABLE audit_findings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id          uuid NOT NULL REFERENCES audit_runs(id),
  snapshot_id       uuid REFERENCES access_snapshots(id),
  employee_id       uuid REFERENCES employees(id),
  system_id         uuid REFERENCES systems(id),
  rule_code         text NOT NULL,
  finding_type      text NOT NULL,
  severity          text NOT NULL CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW','REVIEW')),
  outcome           text NOT NULL CHECK (outcome IN ('VIOLATION','COVERED_BY_EXCEPTION','EXCEPTION_EXPIRED','NEEDS_REVIEW','COMPENSATED')),
  expected          text,
  actual            text,
  explanation       text NOT NULL,
  details           jsonb,
  exception_id      uuid REFERENCES exceptions(id),
  finding_key       text NOT NULL,
  status            text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CONFIRMED','DISPUTED','ACCEPTED_RISK','REMEDIATION','CLOSED')),
  status_changed_by uuid REFERENCES users(id),
  status_changed_at timestamptz
);
CREATE INDEX audit_findings_audit_idx ON audit_findings (audit_id, severity);

CREATE TABLE finding_comments (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id  uuid NOT NULL REFERENCES audit_findings(id),
  author_id   uuid NOT NULL REFERENCES users(id),
  text        text NOT NULL,
  new_status  text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ===================== Сравнение снимков =====================
CREATE TABLE audit_comparisons (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_audit_id  uuid NOT NULL REFERENCES audit_runs(id),
  to_audit_id    uuid NOT NULL REFERENCES audit_runs(id),
  created_by     uuid REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  summary        jsonb
);

CREATE TABLE comparison_items (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  comparison_id  uuid NOT NULL REFERENCES audit_comparisons(id),
  access_key     text NOT NULL,
  change_type    text NOT NULL CHECK (change_type IN ('ADDED','REMOVED','UNCHANGED','CHANGED','NEW_FINDING','RESOLVED','PERSISTING','AMBIGUOUS')),
  before_json    jsonb,
  after_json     jsonb
);
CREATE INDEX comparison_items_idx ON comparison_items (comparison_id, change_type);

-- ===================== Отчёты =====================
CREATE TABLE reports (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id     uuid NOT NULL REFERENCES audit_runs(id),
  format       text NOT NULL CHECK (format IN ('XLSX','PDF')),
  file_name    text NOT NULL,
  stored_path  text NOT NULL,
  sha256       text NOT NULL,
  filters      jsonb,
  created_by   uuid REFERENCES users(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ===================== Журнал действий =====================
CREATE TABLE activity_logs (
  id             bigserial PRIMARY KEY,
  actor_user_id  uuid REFERENCES users(id),
  actor_name     text,
  action         text NOT NULL,
  category       text NOT NULL DEFAULT 'GENERAL' CHECK (category IN ('GENERAL','ADMIN','AUTH','DATA','AUDIT')),
  entity_type    text,
  entity_id      text,
  before_json    jsonb,
  after_json     jsonb,
  ip             text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX activity_logs_created_idx ON activity_logs (created_at DESC);

-- Журнал неизменяем: запрет UPDATE/DELETE на уровне БД.
CREATE OR REPLACE FUNCTION ara_forbid_modification() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Таблица % неизменяема', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER activity_logs_immutable
  BEFORE UPDATE OR DELETE ON activity_logs
  FOR EACH ROW EXECUTE FUNCTION ara_forbid_modification();

-- Снимки завершённых аудитов неизменяемы.
CREATE OR REPLACE FUNCTION ara_protect_completed_snapshot() RETURNS trigger AS $$
DECLARE st text;
BEGIN
  SELECT status INTO st FROM audit_runs WHERE id = COALESCE(OLD.audit_id, NEW.audit_id);
  IF st = 'COMPLETED' THEN
    RAISE EXCEPTION 'Снимок завершённого аудита неизменяем';
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER access_snapshots_protect
  BEFORE UPDATE OR DELETE ON access_snapshots
  FOR EACH ROW EXECUTE FUNCTION ara_protect_completed_snapshot();

-- Утверждённая версия матрицы не редактируется: правила можно менять только в черновике.
CREATE OR REPLACE FUNCTION ara_protect_approved_matrix() RETURNS trigger AS $$
DECLARE st text;
BEGIN
  SELECT status INTO st FROM matrix_versions WHERE id = COALESCE(NEW.version_id, OLD.version_id);
  IF st <> 'DRAFT' THEN
    RAISE EXCEPTION 'Правила утверждённой/архивной версии матрицы изменять нельзя — создайте новую версию';
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER matrix_rules_protect
  BEFORE INSERT OR UPDATE OR DELETE ON matrix_rules
  FOR EACH ROW EXECUTE FUNCTION ara_protect_approved_matrix();

-- Базовые роли и разрешения приложения.
INSERT INTO app_roles (code, name) VALUES
  ('SYS_ADMIN',    'Системный администратор'),
  ('MATRIX_ADMIN', 'Администратор матрицы'),
  ('AUDITOR',      'Аудитор ИБ'),
  ('SYSTEM_OWNER', 'Владелец системы'),
  ('VIEWER',       'Наблюдатель / Руководитель');

INSERT INTO app_role_permissions (role_id, permission_code)
SELECT r.id, p FROM app_roles r, unnest(CASE r.code
  WHEN 'SYS_ADMIN'    THEN ARRAY['users.manage','settings.manage','backup.manage','activity.view','reference.view','dashboard.view','audit.view']
  WHEN 'MATRIX_ADMIN' THEN ARRAY['reference.view','reference.edit','matrix.edit','matrix.approve','sod.edit','exceptions.view','exceptions.edit','dashboard.view','audit.view']
  WHEN 'AUDITOR'      THEN ARRAY['reference.view','dashboard.view','audit.view','audit.create','import.run','audit.run','findings.view','findings.edit','findings.comment','reports.export','exceptions.view','exceptions.edit','comparisons.run','activity.view']
  WHEN 'SYSTEM_OWNER' THEN ARRAY['reference.view','dashboard.view','audit.view','findings.view','findings.comment','findings.scoped','exceptions.view']
  WHEN 'VIEWER'       THEN ARRAY['reference.view','dashboard.view','audit.view','findings.view','reports.export','exceptions.view']
END) AS p;

INSERT INTO app_settings (key, value) VALUES
  ('session_idle_minutes', '30'),
  ('session_max_hours', '10'),
  ('max_failed_logins', '5'),
  ('lockout_minutes', '15'),
  ('max_upload_mb', '50'),
  ('retention_days', '1825'),
  ('severity_policy', '{"TERMINATED_USER_ACCESS":"CRITICAL","ROLE_NOT_ALLOWED":"HIGH","EXCESS_OPERATION":"MEDIUM","SCOPE_MISMATCH":"MEDIUM","EXPLICITLY_DENIED":"HIGH","RESIDUAL_AFTER_TRANSFER":"MEDIUM","NOT_IN_MATRIX":"REVIEW","IDENTITY_UNRESOLVED":"REVIEW","UNKNOWN_REFERENCE":"REVIEW","EXCEPTION_EXPIRED":"HIGH","MATRIX_DEVIATION_WITH_EXCEPTION":"REVIEW","SOD_CONFLICT_COMPENSATED":"REVIEW","LEAVE_USER_ACCESS":"LOW","escalate_by_operation_risk":true}');
