CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
    "MigrationId" character varying(150) NOT NULL,
    "ProductVersion" character varying(32) NOT NULL,
    CONSTRAINT "PK___EFMigrationsHistory" PRIMARY KEY ("MigrationId")
);

START TRANSACTION;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE SEQUENCE asset_event_seq START WITH 1 INCREMENT BY 1 NO CYCLE;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AccessSystems" (
        "Id" uuid NOT NULL,
        "Owner" character varying(256),
        "Criticality" character varying(64),
        "ReviewIntervalMonths" integer,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_AccessSystems" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetCategories" (
        "Id" uuid NOT NULL,
        "ParentId" uuid,
        "DefaultUsefulLifeMonths" integer,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_AssetCategories" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AssetCategories_AssetCategories_ParentId" FOREIGN KEY ("ParentId") REFERENCES "AssetCategories" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetStatuses" (
        "Id" uuid NOT NULL,
        "Kind" integer NOT NULL,
        "Color" character varying(32),
        "IsSystem" boolean NOT NULL,
        "IsDefaultForKind" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_AssetStatuses" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AuditLogs" (
        "Id" bigint GENERATED ALWAYS AS IDENTITY,
        "OrganizationId" uuid NOT NULL,
        "Timestamp" timestamp with time zone NOT NULL,
        "UserId" uuid,
        "UserName" character varying(128),
        "IpAddress" character varying(64),
        "UserAgent" character varying(300),
        "Action" character varying(128) NOT NULL,
        "EntityType" character varying(64),
        "EntityId" uuid,
        "EntityName" character varying(512),
        "OldValues" jsonb,
        "NewValues" jsonb,
        "Comment" text,
        "CorrelationId" character varying(64),
        "Success" boolean NOT NULL,
        CONSTRAINT "PK_AuditLogs" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Backups" (
        "Id" uuid NOT NULL,
        "FileName" character varying(256) NOT NULL,
        "FilePath" character varying(1024) NOT NULL,
        "Size" bigint NOT NULL,
        "Sha256" text,
        "Kind" integer NOT NULL,
        "Status" integer NOT NULL,
        "StartedAt" timestamp with time zone NOT NULL,
        "CompletedAt" timestamp with time zone,
        "CreatedById" uuid,
        "CreatedByName" character varying(128),
        "Error" text,
        "IncludesFiles" boolean NOT NULL,
        "AppVersion" character varying(32),
        CONSTRAINT "PK_Backups" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "ChecklistTemplates" (
        "Id" uuid NOT NULL,
        "Kind" integer NOT NULL,
        "DepartmentId" uuid,
        "PositionId" uuid,
        "RegionId" uuid,
        "IsDefault" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_ChecklistTemplates" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "DocumentTemplates" (
        "Id" uuid NOT NULL,
        "DocumentType" integer NOT NULL,
        "IsDefault" boolean NOT NULL,
        "ActiveVersionId" uuid,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_DocumentTemplates" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "EmployeeStatuses" (
        "Id" uuid NOT NULL,
        "Kind" integer NOT NULL,
        "Color" character varying(32),
        "IsSystem" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_EmployeeStatuses" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "ImportJobs" (
        "Id" uuid NOT NULL,
        "EntityType" character varying(64) NOT NULL,
        "FileId" uuid NOT NULL,
        "FileName" character varying(512) NOT NULL,
        "Status" integer NOT NULL,
        "Mapping" jsonb,
        "TotalRows" integer NOT NULL,
        "ValidRows" integer NOT NULL,
        "ErrorRows" integer NOT NULL,
        "ImportedRows" integer NOT NULL,
        "Errors" jsonb,
        "Options" jsonb,
        "CompletedAt" timestamp with time zone,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_ImportJobs" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "LicenseTypes" (
        "Id" uuid NOT NULL,
        "Model" integer NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_LicenseTypes" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Manufacturers" (
        "Id" uuid NOT NULL,
        "Website" character varying(256),
        "SupportPhone" character varying(64),
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Manufacturers" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "NotificationDeliveries" (
        "Id" uuid NOT NULL,
        "NotificationId" uuid NOT NULL,
        "Channel" character varying(32) NOT NULL,
        "Recipient" character varying(256) NOT NULL,
        "Success" boolean NOT NULL,
        "Error" text,
        "CreatedAt" timestamp with time zone NOT NULL,
        CONSTRAINT "PK_NotificationDeliveries" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "NotificationReads" (
        "NotificationId" uuid NOT NULL,
        "UserId" uuid NOT NULL,
        "ReadAt" timestamp with time zone NOT NULL,
        CONSTRAINT "PK_NotificationReads" PRIMARY KEY ("NotificationId", "UserId")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Notifications" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "Type" character varying(64) NOT NULL,
        "Severity" integer NOT NULL,
        "Title" character varying(512) NOT NULL,
        "Message" character varying(2000) NOT NULL,
        "EntityType" character varying(64),
        "EntityId" uuid,
        "Link" character varying(512),
        "RegionId" uuid,
        "RequiredPermission" character varying(64),
        "UserId" uuid,
        "DedupKey" character varying(256) NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "IsResolved" boolean NOT NULL,
        "ResolvedAt" timestamp with time zone,
        CONSTRAINT "PK_Notifications" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "NumberSequences" (
        "OrganizationId" uuid NOT NULL,
        "Key" character varying(128) NOT NULL,
        "NextValue" bigint NOT NULL,
        CONSTRAINT "PK_NumberSequences" PRIMARY KEY ("OrganizationId", "Key")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Organizations" (
        "Id" uuid NOT NULL,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "IsActive" boolean NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        CONSTRAINT "PK_Organizations" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Permissions" (
        "Code" character varying(64) NOT NULL,
        "Group" character varying(128) NOT NULL,
        "Description" character varying(512) NOT NULL,
        CONSTRAINT "PK_Permissions" PRIMARY KEY ("Code")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Positions" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Positions" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Regions" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Regions" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "RepairStatuses" (
        "Id" uuid NOT NULL,
        "Stage" integer NOT NULL,
        "Color" character varying(32),
        "IsSystem" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_RepairStatuses" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Roles" (
        "Id" uuid NOT NULL,
        "Name" character varying(128) NOT NULL,
        "Code" character varying(64) NOT NULL,
        "Description" text,
        "IsSystem" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_Roles" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Settings" (
        "OrganizationId" uuid NOT NULL,
        "Key" character varying(64) NOT NULL,
        "Value" jsonb NOT NULL,
        "UpdatedAt" timestamp with time zone NOT NULL,
        "UpdatedById" uuid,
        CONSTRAINT "PK_Settings" PRIMARY KEY ("OrganizationId", "Key")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Software" (
        "Id" uuid NOT NULL,
        "Publisher" character varying(256),
        "Version" character varying(64),
        "Category" character varying(128),
        "RequiresLicense" boolean NOT NULL,
        "Website" character varying(256),
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Software" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "StockItems" (
        "Id" uuid NOT NULL,
        "Sku" character varying(64),
        "Category" character varying(128),
        "Unit" character varying(16) NOT NULL,
        "MinQuantity" numeric(18,3) NOT NULL,
        "UnitPrice" numeric(18,2),
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_StockItems" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "StoredFiles" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "FileName" character varying(512) NOT NULL,
        "ContentType" character varying(128) NOT NULL,
        "StoragePath" character varying(1024) NOT NULL,
        "Size" bigint NOT NULL,
        "Sha256" character varying(128) NOT NULL,
        "Category" integer NOT NULL,
        "EntityType" character varying(64),
        "EntityId" uuid,
        "Description" text,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "CreatedByName" text,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_StoredFiles" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Suppliers" (
        "Id" uuid NOT NULL,
        "ContactPerson" character varying(256),
        "Phone" character varying(64),
        "Email" character varying(256),
        "Address" character varying(512),
        "TaxId" character varying(64),
        "Website" character varying(256),
        "IsSupplier" boolean NOT NULL,
        "IsServiceCenter" boolean NOT NULL,
        "IsVendor" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Suppliers" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AccessLevels" (
        "Id" uuid NOT NULL,
        "AccessSystemId" uuid,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_AccessLevels" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AccessLevels_AccessSystems_AccessSystemId" FOREIGN KEY ("AccessSystemId") REFERENCES "AccessSystems" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetTypes" (
        "Id" uuid NOT NULL,
        "CategoryId" uuid,
        "Prefix" character varying(16) NOT NULL,
        "InventoryNumberFormat" character varying(64),
        "Icon" character varying(64),
        "RequireSerialNumber" boolean NOT NULL,
        "UsefulLifeMonths" integer,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_AssetTypes" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AssetTypes_AssetCategories_CategoryId" FOREIGN KEY ("CategoryId") REFERENCES "AssetCategories" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "ChecklistTemplateItems" (
        "Id" uuid NOT NULL,
        "TemplateId" uuid NOT NULL,
        "Title" character varying(512) NOT NULL,
        "Description" text,
        "ActionType" integer NOT NULL,
        "TargetId" uuid,
        "IsRequired" boolean NOT NULL,
        "SortOrder" integer NOT NULL,
        CONSTRAINT "PK_ChecklistTemplateItems" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_ChecklistTemplateItems_ChecklistTemplates_TemplateId" FOREIGN KEY ("TemplateId") REFERENCES "ChecklistTemplates" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Locations" (
        "Id" uuid NOT NULL,
        "Type" integer NOT NULL,
        "RegionId" uuid NOT NULL,
        "ParentId" uuid,
        "Address" character varying(512),
        "FullPath" character varying(1024),
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Locations" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Locations_Locations_ParentId" FOREIGN KEY ("ParentId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Locations_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "RolePermissions" (
        "RoleId" uuid NOT NULL,
        "PermissionCode" character varying(64) NOT NULL,
        CONSTRAINT "PK_RolePermissions" PRIMARY KEY ("RoleId", "PermissionCode"),
        CONSTRAINT "FK_RolePermissions_Permissions_PermissionCode" FOREIGN KEY ("PermissionCode") REFERENCES "Permissions" ("Code") ON DELETE CASCADE,
        CONSTRAINT "FK_RolePermissions_Roles_RoleId" FOREIGN KEY ("RoleId") REFERENCES "Roles" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "StockMovements" (
        "Id" uuid NOT NULL,
        "StockItemId" uuid NOT NULL,
        "Type" integer NOT NULL,
        "Quantity" numeric(18,3) NOT NULL,
        "FromLocationId" uuid,
        "ToLocationId" uuid,
        "EmployeeId" uuid,
        "AssetId" uuid,
        "RepairId" uuid,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "DocumentNumber" character varying(128),
        "Comment" text,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_StockMovements" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_StockMovements_StockItems_StockItemId" FOREIGN KEY ("StockItemId") REFERENCES "StockItems" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "DocumentTemplateVersions" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "TemplateId" uuid NOT NULL,
        "VersionNumber" integer NOT NULL,
        "FileId" uuid NOT NULL,
        "FileHash" character varying(128) NOT NULL,
        "ChangeNote" text,
        "Placeholders" jsonb,
        "IsActive" boolean NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "CreatedByName" text,
        CONSTRAINT "PK_DocumentTemplateVersions" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_DocumentTemplateVersions_DocumentTemplates_TemplateId" FOREIGN KEY ("TemplateId") REFERENCES "DocumentTemplates" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_DocumentTemplateVersions_StoredFiles_FileId" FOREIGN KEY ("FileId") REFERENCES "StoredFiles" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Contracts" (
        "Id" uuid NOT NULL,
        "Number" character varying(128) NOT NULL,
        "Title" character varying(512) NOT NULL,
        "Type" integer NOT NULL,
        "SupplierId" uuid,
        "StartDate" date,
        "EndDate" date,
        "Amount" numeric(18,2),
        "Currency" character varying(8),
        "Notes" text,
        "RegionId" uuid,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Contracts" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Contracts_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Contracts_Suppliers_SupplierId" FOREIGN KEY ("SupplierId") REFERENCES "Suppliers" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "CustomFieldDefinitions" (
        "Id" uuid NOT NULL,
        "EntityType" integer NOT NULL,
        "AssetTypeId" uuid,
        "Key" character varying(64) NOT NULL,
        "Label" character varying(256) NOT NULL,
        "DataType" integer NOT NULL,
        "Options" jsonb,
        "IsRequired" boolean NOT NULL,
        "IsSearchable" boolean NOT NULL,
        "ShowInList" boolean NOT NULL,
        "DefaultValue" text,
        "HelpText" text,
        "Group" character varying(128),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_CustomFieldDefinitions" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_CustomFieldDefinitions_AssetTypes_AssetTypeId" FOREIGN KEY ("AssetTypeId") REFERENCES "AssetTypes" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "InventoryCampaigns" (
        "Id" uuid NOT NULL,
        "Number" character varying(64) NOT NULL,
        "Name" character varying(256) NOT NULL,
        "RegionId" uuid,
        "LocationId" uuid,
        "DepartmentId" uuid,
        "Status" integer NOT NULL,
        "StartedAt" timestamp with time zone,
        "CompletedAt" timestamp with time zone,
        "Comment" text,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_InventoryCampaigns" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_InventoryCampaigns_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_InventoryCampaigns_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "StockBalances" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "StockItemId" uuid NOT NULL,
        "LocationId" uuid NOT NULL,
        "Quantity" numeric(18,3) NOT NULL,
        CONSTRAINT "PK_StockBalances" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_StockBalances_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_StockBalances_StockItems_StockItemId" FOREIGN KEY ("StockItemId") REFERENCES "StockItems" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "GeneratedDocuments" (
        "Id" uuid NOT NULL,
        "Number" character varying(64) NOT NULL,
        "Title" character varying(512) NOT NULL,
        "DocumentType" integer NOT NULL,
        "TemplateId" uuid,
        "TemplateVersionId" uuid,
        "TemplateVersionNumber" integer NOT NULL,
        "SourceType" character varying(64) NOT NULL,
        "SourceId" uuid,
        "EmployeeId" uuid,
        "AssetId" uuid,
        "RegionId" uuid,
        "DocxFileId" uuid,
        "PdfFileId" uuid,
        "DataSnapshot" jsonb,
        "EmployeeSignatureStatus" integer NOT NULL,
        "ResponsibleSignatureStatus" integer NOT NULL,
        "EmployeeSignedAt" timestamp with time zone,
        "ResponsibleSignedAt" timestamp with time zone,
        "SignatureMethod" integer NOT NULL,
        "SignedScanFileId" uuid,
        "IsVoided" boolean NOT NULL,
        "VoidReason" text,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_GeneratedDocuments" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_GeneratedDocuments_DocumentTemplateVersions_TemplateVersion~" FOREIGN KEY ("TemplateVersionId") REFERENCES "DocumentTemplateVersions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_GeneratedDocuments_StoredFiles_DocxFileId" FOREIGN KEY ("DocxFileId") REFERENCES "StoredFiles" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_GeneratedDocuments_StoredFiles_PdfFileId" FOREIGN KEY ("PdfFileId") REFERENCES "StoredFiles" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Licenses" (
        "Id" uuid NOT NULL,
        "Name" character varying(256) NOT NULL,
        "SoftwareId" uuid,
        "VendorId" uuid,
        "SupplierId" uuid,
        "LicenseTypeId" uuid,
        "Model" integer NOT NULL,
        "LicenseKeyEncrypted" text,
        "Seats" integer NOT NULL,
        "PurchaseDate" date,
        "ExpirationDate" date,
        "RenewalDate" date,
        "Cost" numeric(18,2),
        "Currency" character varying(8),
        "ContractId" uuid,
        "ContractNumber" character varying(128),
        "Notes" text,
        "RegionId" uuid,
        "IsArchived" boolean NOT NULL,
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Licenses" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Licenses_Contracts_ContractId" FOREIGN KEY ("ContractId") REFERENCES "Contracts" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Licenses_LicenseTypes_LicenseTypeId" FOREIGN KEY ("LicenseTypeId") REFERENCES "LicenseTypes" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Licenses_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Licenses_Software_SoftwareId" FOREIGN KEY ("SoftwareId") REFERENCES "Software" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Licenses_Suppliers_SupplierId" FOREIGN KEY ("SupplierId") REFERENCES "Suppliers" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Licenses_Suppliers_VendorId" FOREIGN KEY ("VendorId") REFERENCES "Suppliers" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "ApiTokens" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "UserId" uuid NOT NULL,
        "Name" character varying(128) NOT NULL,
        "TokenHash" character varying(128) NOT NULL,
        "Prefix" character varying(16) NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "ExpiresAt" timestamp with time zone,
        "LastUsedAt" timestamp with time zone,
        "RevokedAt" timestamp with time zone,
        CONSTRAINT "PK_ApiTokens" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetEvents" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "AssetId" uuid NOT NULL,
        "Sequence" bigint NOT NULL DEFAULT (nextval('asset_event_seq')),
        "EventType" integer NOT NULL,
        "AffectsState" boolean NOT NULL,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "RecordedByName" character varying(256),
        "OperationType" integer,
        "OperationId" uuid,
        "BatchId" uuid,
        "StatusId" uuid,
        "EmployeeId" uuid,
        "DepartmentId" uuid,
        "RegionId" uuid,
        "LocationId" uuid,
        "Delta" jsonb,
        "Data" jsonb,
        "Description" character varying(2000),
        "IsCancelled" boolean NOT NULL,
        "CancelledAt" timestamp with time zone,
        "CancelledById" uuid,
        "CancelReason" character varying(1000),
        CONSTRAINT "PK_AssetEvents" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetReturns" (
        "Id" uuid NOT NULL,
        "BatchId" uuid NOT NULL,
        "AssetId" uuid NOT NULL,
        "EmployeeId" uuid NOT NULL,
        "AssignmentId" uuid,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "Condition" integer NOT NULL,
        "Accessories" text,
        "Damage" text,
        "MissingItems" text,
        "Comment" text,
        "ResponsibleEmployeeId" uuid,
        "ResultStatusId" uuid,
        "LocationId" uuid,
        "RepairId" uuid,
        "AssetSnapshot" jsonb,
        "EmployeeSnapshot" jsonb,
        "IsCancelled" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_AssetReturns" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AssetReturns_AssetStatuses_ResultStatusId" FOREIGN KEY ("ResultStatusId") REFERENCES "AssetStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_AssetReturns_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Assets" (
        "Id" uuid NOT NULL,
        "InventoryNumber" character varying(64) NOT NULL,
        "Name" character varying(256) NOT NULL,
        "AssetTypeId" uuid NOT NULL,
        "CategoryId" uuid,
        "ManufacturerId" uuid,
        "Model" character varying(256),
        "SerialNumber" character varying(128),
        "StatusId" uuid NOT NULL,
        "EmployeeId" uuid,
        "DepartmentId" uuid,
        "RegionId" uuid NOT NULL,
        "LocationId" uuid,
        "ResponsibleEmployeeId" uuid,
        "ParentAssetId" uuid,
        "Hostname" character varying(128),
        "IpAddress" character varying(64),
        "MacAddress" character varying(64),
        "PurchaseDate" date,
        "PurchasePrice" numeric(18,2),
        "Currency" character varying(8),
        "SupplierId" uuid,
        "ContractId" uuid,
        "InvoiceNumber" character varying(128),
        "WarrantyExpiration" date,
        "DepreciationMethod" integer NOT NULL,
        "UsefulLifeMonths" integer,
        "SalvageValue" numeric(18,2),
        "Condition" integer NOT NULL,
        "Notes" text,
        "CustomFields" jsonb,
        "LastInventoryAt" timestamp with time zone,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Assets" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Assets_AssetCategories_CategoryId" FOREIGN KEY ("CategoryId") REFERENCES "AssetCategories" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_AssetStatuses_StatusId" FOREIGN KEY ("StatusId") REFERENCES "AssetStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_AssetTypes_AssetTypeId" FOREIGN KEY ("AssetTypeId") REFERENCES "AssetTypes" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Assets_ParentAssetId" FOREIGN KEY ("ParentAssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Contracts_ContractId" FOREIGN KEY ("ContractId") REFERENCES "Contracts" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Manufacturers_ManufacturerId" FOREIGN KEY ("ManufacturerId") REFERENCES "Manufacturers" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assets_Suppliers_SupplierId" FOREIGN KEY ("SupplierId") REFERENCES "Suppliers" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "InventoryCampaignItems" (
        "Id" uuid NOT NULL,
        "CampaignId" uuid NOT NULL,
        "AssetId" uuid NOT NULL,
        "ExpectedLocationId" uuid,
        "ExpectedEmployeeId" uuid,
        "FoundLocationId" uuid,
        "Result" integer NOT NULL,
        "CheckedAt" timestamp with time zone,
        "CheckedById" uuid,
        "CheckedByName" text,
        "Condition" integer,
        "Comment" text,
        CONSTRAINT "PK_InventoryCampaignItems" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_InventoryCampaignItems_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE CASCADE,
        CONSTRAINT "FK_InventoryCampaignItems_InventoryCampaigns_CampaignId" FOREIGN KEY ("CampaignId") REFERENCES "InventoryCampaigns" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Repairs" (
        "Id" uuid NOT NULL,
        "Number" character varying(64) NOT NULL,
        "AssetId" uuid NOT NULL,
        "StatusId" uuid NOT NULL,
        "OpenedAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "SentAt" timestamp with time zone,
        "ServiceCenterId" uuid,
        "Problem" character varying(4000) NOT NULL,
        "Diagnosis" text,
        "RepairDescription" text,
        "Parts" text,
        "Cost" numeric(18,2),
        "Currency" character varying(8),
        "IsWarranty" boolean NOT NULL,
        "ExpectedReturnDate" date,
        "ActualReturnAt" timestamp with time zone,
        "Technician" character varying(256),
        "Comment" text,
        "EmployeeId" uuid,
        "PreviousStatusId" uuid,
        "ReturnStatusId" uuid,
        "OpenEventId" uuid,
        "CloseEventId" uuid,
        "RegionId" uuid,
        "AssetSnapshot" jsonb,
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Repairs" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Repairs_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Repairs_RepairStatuses_StatusId" FOREIGN KEY ("StatusId") REFERENCES "RepairStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Repairs_Suppliers_ServiceCenterId" FOREIGN KEY ("ServiceCenterId") REFERENCES "Suppliers" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "RepairStatusHistory" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "RepairId" uuid NOT NULL,
        "StatusId" uuid NOT NULL,
        "StatusName" character varying(256) NOT NULL,
        "ChangedAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "RecordedByName" text,
        "Comment" text,
        CONSTRAINT "PK_RepairStatusHistory" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_RepairStatusHistory_Repairs_RepairId" FOREIGN KEY ("RepairId") REFERENCES "Repairs" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetStatusChanges" (
        "Id" uuid NOT NULL,
        "BatchId" uuid,
        "AssetId" uuid NOT NULL,
        "Number" character varying(64) NOT NULL,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "FromStatusId" uuid NOT NULL,
        "ToStatusId" uuid NOT NULL,
        "ReservedForEmployeeId" uuid,
        "ReservedUntil" date,
        "Reason" text,
        "Comment" text,
        "DisposalMethod" text,
        "ClosedAssignmentId" uuid,
        "Snapshot" jsonb,
        "IsCancelled" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_AssetStatusChanges" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AssetStatusChanges_AssetStatuses_FromStatusId" FOREIGN KEY ("FromStatusId") REFERENCES "AssetStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_AssetStatusChanges_AssetStatuses_ToStatusId" FOREIGN KEY ("ToStatusId") REFERENCES "AssetStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_AssetStatusChanges_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "AssetTransfers" (
        "Id" uuid NOT NULL,
        "BatchId" uuid NOT NULL,
        "AssetId" uuid NOT NULL,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "FromEmployeeId" uuid,
        "FromDepartmentId" uuid,
        "FromRegionId" uuid,
        "FromLocationId" uuid,
        "ToEmployeeId" uuid,
        "ToDepartmentId" uuid,
        "ToRegionId" uuid,
        "ToLocationId" uuid,
        "ResponsibleEmployeeId" uuid,
        "Reason" character varying(1000),
        "Comment" text,
        "Snapshot" jsonb,
        "ClosedAssignmentId" uuid,
        "NewAssignmentId" uuid,
        "IsCancelled" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_AssetTransfers" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AssetTransfers_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Assignments" (
        "Id" uuid NOT NULL,
        "BatchId" uuid NOT NULL,
        "AssetId" uuid NOT NULL,
        "EmployeeId" uuid NOT NULL,
        "EffectiveFrom" timestamp with time zone NOT NULL,
        "EffectiveTo" timestamp with time zone,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "LocationId" uuid,
        "ResponsibleEmployeeId" uuid,
        "Condition" integer NOT NULL,
        "Accessories" text,
        "Comment" text,
        "ExpectedReturnDate" date,
        "ReturnId" uuid,
        "CloseReason" text,
        "AssetSnapshot" jsonb,
        "EmployeeSnapshot" jsonb,
        "IsCancelled" boolean NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_Assignments" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Assignments_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Assignments_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Departments" (
        "Id" uuid NOT NULL,
        "Type" integer NOT NULL,
        "ParentId" uuid,
        "RegionId" uuid,
        "HeadEmployeeId" uuid,
        "CostCenter" character varying(64),
        "FullPath" character varying(1024),
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "Name" character varying(256) NOT NULL,
        "Code" character varying(64),
        "Description" character varying(2000),
        "SortOrder" integer NOT NULL,
        "IsArchived" boolean NOT NULL,
        CONSTRAINT "PK_Departments" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Departments_Departments_ParentId" FOREIGN KEY ("ParentId") REFERENCES "Departments" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Departments_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Employees" (
        "Id" uuid NOT NULL,
        "EmployeeNumber" character varying(64) NOT NULL,
        "LastName" character varying(128) NOT NULL,
        "FirstName" character varying(128) NOT NULL,
        "MiddleName" character varying(128),
        "FullName" character varying(400) NOT NULL,
        "Login" character varying(128),
        "Email" character varying(256),
        "Phone" character varying(64),
        "PositionId" uuid,
        "DepartmentId" uuid,
        "RegionId" uuid NOT NULL,
        "LocationId" uuid,
        "RoomId" uuid,
        "ManagerId" uuid,
        "HireDate" date,
        "TerminationDate" date,
        "StatusId" uuid NOT NULL,
        "Comment" text,
        "PhotoFileId" uuid,
        "CustomFields" jsonb,
        "ExternalId" character varying(256),
        "ExternalSource" character varying(64),
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Employees" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Employees_Departments_DepartmentId" FOREIGN KEY ("DepartmentId") REFERENCES "Departments" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_EmployeeStatuses_StatusId" FOREIGN KEY ("StatusId") REFERENCES "EmployeeStatuses" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_Employees_ManagerId" FOREIGN KEY ("ManagerId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_Locations_LocationId" FOREIGN KEY ("LocationId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_Locations_RoomId" FOREIGN KEY ("RoomId") REFERENCES "Locations" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_Positions_PositionId" FOREIGN KEY ("PositionId") REFERENCES "Positions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_Employees_StoredFiles_PhotoFileId" FOREIGN KEY ("PhotoFileId") REFERENCES "StoredFiles" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "EmployeeAccesses" (
        "Id" uuid NOT NULL,
        "EmployeeId" uuid NOT NULL,
        "AccessSystemId" uuid NOT NULL,
        "AccessLevelId" uuid,
        "Username" character varying(256),
        "Role" character varying(256),
        "GrantedAt" timestamp with time zone NOT NULL,
        "RevokedAt" timestamp with time zone,
        "RecordedAt" timestamp with time zone NOT NULL,
        "Status" integer NOT NULL,
        "ResponsibleEmployeeId" uuid,
        "RequestReference" character varying(128),
        "ReviewDueDate" date,
        "LastReviewedAt" timestamp with time zone,
        "Comment" text,
        "RevokeReason" text,
        "CustomFields" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_EmployeeAccesses" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_EmployeeAccesses_AccessLevels_AccessLevelId" FOREIGN KEY ("AccessLevelId") REFERENCES "AccessLevels" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_EmployeeAccesses_AccessSystems_AccessSystemId" FOREIGN KEY ("AccessSystemId") REFERENCES "AccessSystems" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_EmployeeAccesses_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_EmployeeAccesses_Employees_ResponsibleEmployeeId" FOREIGN KEY ("ResponsibleEmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "EmployeeChecklists" (
        "Id" uuid NOT NULL,
        "EmployeeId" uuid NOT NULL,
        "TemplateId" uuid,
        "Title" character varying(512) NOT NULL,
        "Kind" integer NOT NULL,
        "Status" integer NOT NULL,
        "StartedAt" timestamp with time zone NOT NULL,
        "DueDate" date,
        "CompletedAt" timestamp with time zone,
        "CompletedById" uuid,
        "Comment" text,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_EmployeeChecklists" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_EmployeeChecklists_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "EmployeeOrgHistory" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "EmployeeId" uuid NOT NULL,
        "EffectiveFrom" timestamp with time zone NOT NULL,
        "EffectiveTo" timestamp with time zone,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "DepartmentId" uuid,
        "PositionId" uuid,
        "RegionId" uuid NOT NULL,
        "LocationId" uuid,
        "ManagerId" uuid,
        "StatusId" uuid,
        "Snapshot" jsonb,
        "Reason" character varying(1000),
        CONSTRAINT "PK_EmployeeOrgHistory" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_EmployeeOrgHistory_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "LicenseAssignments" (
        "Id" uuid NOT NULL,
        "LicenseId" uuid NOT NULL,
        "EmployeeId" uuid,
        "AssetId" uuid,
        "AssignedAt" timestamp with time zone NOT NULL,
        "RevokedAt" timestamp with time zone,
        "RecordedAt" timestamp with time zone NOT NULL,
        "RecordedById" uuid,
        "SeatCount" integer NOT NULL,
        "Comment" text,
        "RevokeReason" text,
        "Snapshot" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_LicenseAssignments" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_LicenseAssignments_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_LicenseAssignments_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_LicenseAssignments_Licenses_LicenseId" FOREIGN KEY ("LicenseId") REFERENCES "Licenses" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "OperationBatches" (
        "Id" uuid NOT NULL,
        "Number" character varying(64) NOT NULL,
        "Type" integer NOT NULL,
        "EffectiveAt" timestamp with time zone NOT NULL,
        "RecordedAt" timestamp with time zone NOT NULL,
        "EmployeeId" uuid,
        "ResponsibleEmployeeId" uuid,
        "RegionId" uuid,
        "Comment" text,
        "EmployeeSnapshot" jsonb,
        "ResponsibleSnapshot" jsonb,
        "IsBackdated" boolean NOT NULL,
        "IsCancelled" boolean NOT NULL,
        "CancelledAt" timestamp with time zone,
        "CancelledById" uuid,
        "CancelReason" character varying(1000),
        "EmployeeSignatureStatus" integer NOT NULL,
        "ResponsibleSignatureStatus" integer NOT NULL,
        "SignedAt" timestamp with time zone,
        "SignatureMethod" integer NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        CONSTRAINT "PK_OperationBatches" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_OperationBatches_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_OperationBatches_Employees_ResponsibleEmployeeId" FOREIGN KEY ("ResponsibleEmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT,
        CONSTRAINT "FK_OperationBatches_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "Users" (
        "Id" uuid NOT NULL,
        "UserName" character varying(128) NOT NULL,
        "NormalizedUserName" character varying(128) NOT NULL,
        "DisplayName" character varying(256) NOT NULL,
        "Email" character varying(256),
        "PasswordHash" text,
        "IsActive" boolean NOT NULL,
        "FailedLoginCount" integer NOT NULL,
        "LockoutEnd" timestamp with time zone,
        "LastLoginAt" timestamp with time zone,
        "LastLoginIp" character varying(64),
        "PasswordChangedAt" timestamp with time zone,
        "MustChangePassword" boolean NOT NULL,
        "EmployeeId" uuid,
        "AuthProvider" character varying(32) NOT NULL,
        "ExternalId" text,
        "AllRegions" boolean NOT NULL,
        "Language" text,
        "TimeZone" text,
        "Preferences" jsonb,
        "OrganizationId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "CreatedById" uuid,
        "UpdatedAt" timestamp with time zone,
        "UpdatedById" uuid,
        "IsDeleted" boolean NOT NULL,
        "DeletedAt" timestamp with time zone,
        "DeletedById" uuid,
        CONSTRAINT "PK_Users" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_Users_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "EmployeeChecklistItems" (
        "Id" uuid NOT NULL,
        "ChecklistId" uuid NOT NULL,
        "Title" character varying(512) NOT NULL,
        "Description" text,
        "ActionType" integer NOT NULL,
        "TargetId" uuid,
        "IsRequired" boolean NOT NULL,
        "SortOrder" integer NOT NULL,
        "IsDone" boolean NOT NULL,
        "DoneAt" timestamp with time zone,
        "DoneById" uuid,
        "DoneByName" text,
        "Comment" text,
        "LinkedEntityType" text,
        "LinkedEntityId" uuid,
        CONSTRAINT "PK_EmployeeChecklistItems" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_EmployeeChecklistItems_EmployeeChecklists_ChecklistId" FOREIGN KEY ("ChecklistId") REFERENCES "EmployeeChecklists" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "UserRegions" (
        "UserId" uuid NOT NULL,
        "RegionId" uuid NOT NULL,
        CONSTRAINT "PK_UserRegions" PRIMARY KEY ("UserId", "RegionId"),
        CONSTRAINT "FK_UserRegions_Regions_RegionId" FOREIGN KEY ("RegionId") REFERENCES "Regions" ("Id") ON DELETE CASCADE,
        CONSTRAINT "FK_UserRegions_Users_UserId" FOREIGN KEY ("UserId") REFERENCES "Users" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "UserRoles" (
        "UserId" uuid NOT NULL,
        "RoleId" uuid NOT NULL,
        CONSTRAINT "PK_UserRoles" PRIMARY KEY ("UserId", "RoleId"),
        CONSTRAINT "FK_UserRoles_Roles_RoleId" FOREIGN KEY ("RoleId") REFERENCES "Roles" ("Id") ON DELETE CASCADE,
        CONSTRAINT "FK_UserRoles_Users_UserId" FOREIGN KEY ("UserId") REFERENCES "Users" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE TABLE "UserSessions" (
        "Id" uuid NOT NULL,
        "UserId" uuid NOT NULL,
        "CreatedAt" timestamp with time zone NOT NULL,
        "LastSeenAt" timestamp with time zone NOT NULL,
        "ExpiresAt" timestamp with time zone NOT NULL,
        "IpAddress" character varying(64),
        "UserAgent" character varying(512),
        "RevokedAt" timestamp with time zone,
        "RevokeReason" text,
        CONSTRAINT "PK_UserSessions" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_UserSessions_Users_UserId" FOREIGN KEY ("UserId") REFERENCES "Users" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AccessLevels_AccessSystemId" ON "AccessLevels" ("AccessSystemId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AccessLevels_OrganizationId_Name" ON "AccessLevels" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AccessSystems_OrganizationId_Name" ON "AccessSystems" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_ApiTokens_TokenHash" ON "ApiTokens" ("TokenHash");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_ApiTokens_UserId" ON "ApiTokens" ("UserId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetCategories_OrganizationId_Name" ON "AssetCategories" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetCategories_ParentId" ON "AssetCategories" ("ParentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetEvents_AssetId_EffectiveAt_Sequence" ON "AssetEvents" ("AssetId", "EffectiveAt", "Sequence");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetEvents_EffectiveAt" ON "AssetEvents" ("EffectiveAt");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetEvents_EmployeeId" ON "AssetEvents" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetEvents_OperationId" ON "AssetEvents" ("OperationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_AssetId" ON "AssetReturns" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_AssignmentId" ON "AssetReturns" ("AssignmentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_BatchId" ON "AssetReturns" ("BatchId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_EmployeeId" ON "AssetReturns" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_LocationId" ON "AssetReturns" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetReturns_ResultStatusId" ON "AssetReturns" ("ResultStatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_AssetTypeId" ON "Assets" ("AssetTypeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_CategoryId" ON "Assets" ("CategoryId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_ContractId" ON "Assets" ("ContractId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_CustomFields" ON "Assets" USING gin ("CustomFields");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_DepartmentId" ON "Assets" ("DepartmentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_EmployeeId" ON "Assets" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_InventoryNumber_trgm" ON "Assets" USING gin ("InventoryNumber" gin_trgm_ops);
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_LocationId" ON "Assets" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_ManufacturerId" ON "Assets" ("ManufacturerId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_Name" ON "Assets" USING gin ("Name" gin_trgm_ops);
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Assets_OrganizationId_InventoryNumber" ON "Assets" ("OrganizationId", "InventoryNumber");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_ParentAssetId" ON "Assets" ("ParentAssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_RegionId" ON "Assets" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_ResponsibleEmployeeId" ON "Assets" ("ResponsibleEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_SerialNumber" ON "Assets" ("SerialNumber");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_StatusId" ON "Assets" ("StatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_SupplierId" ON "Assets" ("SupplierId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assets_WarrantyExpiration" ON "Assets" ("WarrantyExpiration");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetStatusChanges_AssetId" ON "AssetStatusChanges" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetStatusChanges_BatchId" ON "AssetStatusChanges" ("BatchId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetStatusChanges_FromStatusId" ON "AssetStatusChanges" ("FromStatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetStatusChanges_ToStatusId" ON "AssetStatusChanges" ("ToStatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetStatuses_OrganizationId_Name" ON "AssetStatuses" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetTransfers_AssetId" ON "AssetTransfers" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetTransfers_BatchId" ON "AssetTransfers" ("BatchId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetTypes_CategoryId" ON "AssetTypes" ("CategoryId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AssetTypes_OrganizationId_Name" ON "AssetTypes" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assignments_AssetId_EffectiveFrom" ON "Assignments" ("AssetId", "EffectiveFrom");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assignments_BatchId" ON "Assignments" ("BatchId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assignments_EmployeeId" ON "Assignments" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assignments_LocationId" ON "Assignments" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Assignments_ResponsibleEmployeeId" ON "Assignments" ("ResponsibleEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "UX_Assignments_OneOpenPerAsset" ON "Assignments" ("AssetId") WHERE "EffectiveTo" IS NULL AND "IsCancelled" = false;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AuditLogs_Action" ON "AuditLogs" ("Action");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AuditLogs_EntityType_EntityId" ON "AuditLogs" ("EntityType", "EntityId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AuditLogs_Timestamp" ON "AuditLogs" ("Timestamp");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_AuditLogs_UserId" ON "AuditLogs" ("UserId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_ChecklistTemplateItems_TemplateId" ON "ChecklistTemplateItems" ("TemplateId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_ChecklistTemplates_OrganizationId_Name" ON "ChecklistTemplates" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Contracts_EndDate" ON "Contracts" ("EndDate");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Contracts_RegionId" ON "Contracts" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Contracts_SupplierId" ON "Contracts" ("SupplierId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_CustomFieldDefinitions_AssetTypeId" ON "CustomFieldDefinitions" ("AssetTypeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_CustomFieldDefinitions_OrganizationId_EntityType_AssetTypeI~" ON "CustomFieldDefinitions" ("OrganizationId", "EntityType", "AssetTypeId", "Key");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Departments_HeadEmployeeId" ON "Departments" ("HeadEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Departments_OrganizationId_Name" ON "Departments" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Departments_ParentId" ON "Departments" ("ParentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Departments_RegionId" ON "Departments" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_DocumentTemplates_OrganizationId_Name" ON "DocumentTemplates" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_DocumentTemplateVersions_FileId" ON "DocumentTemplateVersions" ("FileId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_DocumentTemplateVersions_TemplateId_VersionNumber" ON "DocumentTemplateVersions" ("TemplateId", "VersionNumber");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeAccesses_AccessLevelId" ON "EmployeeAccesses" ("AccessLevelId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeAccesses_AccessSystemId_Status" ON "EmployeeAccesses" ("AccessSystemId", "Status");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeAccesses_EmployeeId" ON "EmployeeAccesses" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeAccesses_ResponsibleEmployeeId" ON "EmployeeAccesses" ("ResponsibleEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeChecklistItems_ChecklistId" ON "EmployeeChecklistItems" ("ChecklistId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeChecklists_EmployeeId_Kind" ON "EmployeeChecklists" ("EmployeeId", "Kind");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeOrgHistory_EmployeeId_EffectiveFrom" ON "EmployeeOrgHistory" ("EmployeeId", "EffectiveFrom");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_DepartmentId" ON "Employees" ("DepartmentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_Email" ON "Employees" ("Email");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_ExternalId" ON "Employees" ("ExternalId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_FullName" ON "Employees" USING gin ("FullName" gin_trgm_ops);
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_LocationId" ON "Employees" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_Login" ON "Employees" ("Login");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_ManagerId" ON "Employees" ("ManagerId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Employees_OrganizationId_EmployeeNumber" ON "Employees" ("OrganizationId", "EmployeeNumber") WHERE "IsDeleted" = false;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_PhotoFileId" ON "Employees" ("PhotoFileId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_PositionId" ON "Employees" ("PositionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_RegionId" ON "Employees" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_RoomId" ON "Employees" ("RoomId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Employees_StatusId" ON "Employees" ("StatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_EmployeeStatuses_OrganizationId_Name" ON "EmployeeStatuses" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_AssetId" ON "GeneratedDocuments" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_DocxFileId" ON "GeneratedDocuments" ("DocxFileId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_EmployeeId" ON "GeneratedDocuments" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_GeneratedDocuments_OrganizationId_Number" ON "GeneratedDocuments" ("OrganizationId", "Number");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_PdfFileId" ON "GeneratedDocuments" ("PdfFileId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_SourceType_SourceId" ON "GeneratedDocuments" ("SourceType", "SourceId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_GeneratedDocuments_TemplateVersionId" ON "GeneratedDocuments" ("TemplateVersionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_InventoryCampaignItems_AssetId" ON "InventoryCampaignItems" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_InventoryCampaignItems_CampaignId_AssetId" ON "InventoryCampaignItems" ("CampaignId", "AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_InventoryCampaigns_LocationId" ON "InventoryCampaigns" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_InventoryCampaigns_RegionId" ON "InventoryCampaigns" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_LicenseAssignments_AssetId" ON "LicenseAssignments" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_LicenseAssignments_EmployeeId" ON "LicenseAssignments" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_LicenseAssignments_LicenseId" ON "LicenseAssignments" ("LicenseId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_ContractId" ON "Licenses" ("ContractId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_ExpirationDate" ON "Licenses" ("ExpirationDate");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_LicenseTypeId" ON "Licenses" ("LicenseTypeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_RegionId" ON "Licenses" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_SoftwareId" ON "Licenses" ("SoftwareId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_SupplierId" ON "Licenses" ("SupplierId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Licenses_VendorId" ON "Licenses" ("VendorId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_LicenseTypes_OrganizationId_Name" ON "LicenseTypes" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Locations_OrganizationId_Name" ON "Locations" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Locations_ParentId" ON "Locations" ("ParentId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Locations_RegionId" ON "Locations" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Manufacturers_OrganizationId_Name" ON "Manufacturers" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Notifications_CreatedAt" ON "Notifications" ("CreatedAt");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Notifications_OrganizationId_DedupKey" ON "Notifications" ("OrganizationId", "DedupKey");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_OperationBatches_EffectiveAt" ON "OperationBatches" ("EffectiveAt");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_OperationBatches_EmployeeId" ON "OperationBatches" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_OperationBatches_OrganizationId_Number" ON "OperationBatches" ("OrganizationId", "Number");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_OperationBatches_RegionId" ON "OperationBatches" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_OperationBatches_ResponsibleEmployeeId" ON "OperationBatches" ("ResponsibleEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Positions_OrganizationId_Name" ON "Positions" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Regions_OrganizationId_Name" ON "Regions" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Repairs_AssetId" ON "Repairs" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Repairs_OpenedAt" ON "Repairs" ("OpenedAt");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Repairs_OrganizationId_Number" ON "Repairs" ("OrganizationId", "Number");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Repairs_ServiceCenterId" ON "Repairs" ("ServiceCenterId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Repairs_StatusId" ON "Repairs" ("StatusId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_RepairStatuses_OrganizationId_Name" ON "RepairStatuses" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_RepairStatusHistory_RepairId" ON "RepairStatusHistory" ("RepairId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_RolePermissions_PermissionCode" ON "RolePermissions" ("PermissionCode");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Roles_OrganizationId_Code" ON "Roles" ("OrganizationId", "Code");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Software_OrganizationId_Name" ON "Software" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_StockBalances_LocationId" ON "StockBalances" ("LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_StockBalances_StockItemId_LocationId" ON "StockBalances" ("StockItemId", "LocationId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_StockItems_OrganizationId_Name" ON "StockItems" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_StockMovements_StockItemId" ON "StockMovements" ("StockItemId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_StoredFiles_EntityType_EntityId" ON "StoredFiles" ("EntityType", "EntityId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Suppliers_OrganizationId_Name" ON "Suppliers" ("OrganizationId", "Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_UserRegions_RegionId" ON "UserRegions" ("RegionId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_UserRoles_RoleId" ON "UserRoles" ("RoleId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_Users_EmployeeId" ON "Users" ("EmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE UNIQUE INDEX "IX_Users_OrganizationId_NormalizedUserName" ON "Users" ("OrganizationId", "NormalizedUserName") WHERE "IsDeleted" = false;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    CREATE INDEX "IX_UserSessions_UserId" ON "UserSessions" ("UserId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "ApiTokens" ADD CONSTRAINT "FK_ApiTokens_Users_UserId" FOREIGN KEY ("UserId") REFERENCES "Users" ("Id") ON DELETE CASCADE;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetEvents" ADD CONSTRAINT "FK_AssetEvents_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetReturns" ADD CONSTRAINT "FK_AssetReturns_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetReturns" ADD CONSTRAINT "FK_AssetReturns_Assignments_AssignmentId" FOREIGN KEY ("AssignmentId") REFERENCES "Assignments" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetReturns" ADD CONSTRAINT "FK_AssetReturns_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetReturns" ADD CONSTRAINT "FK_AssetReturns_OperationBatches_BatchId" FOREIGN KEY ("BatchId") REFERENCES "OperationBatches" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assets" ADD CONSTRAINT "FK_Assets_Departments_DepartmentId" FOREIGN KEY ("DepartmentId") REFERENCES "Departments" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assets" ADD CONSTRAINT "FK_Assets_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assets" ADD CONSTRAINT "FK_Assets_Employees_ResponsibleEmployeeId" FOREIGN KEY ("ResponsibleEmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetStatusChanges" ADD CONSTRAINT "FK_AssetStatusChanges_OperationBatches_BatchId" FOREIGN KEY ("BatchId") REFERENCES "OperationBatches" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "AssetTransfers" ADD CONSTRAINT "FK_AssetTransfers_OperationBatches_BatchId" FOREIGN KEY ("BatchId") REFERENCES "OperationBatches" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assignments" ADD CONSTRAINT "FK_Assignments_Employees_EmployeeId" FOREIGN KEY ("EmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assignments" ADD CONSTRAINT "FK_Assignments_Employees_ResponsibleEmployeeId" FOREIGN KEY ("ResponsibleEmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Assignments" ADD CONSTRAINT "FK_Assignments_OperationBatches_BatchId" FOREIGN KEY ("BatchId") REFERENCES "OperationBatches" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    ALTER TABLE "Departments" ADD CONSTRAINT "FK_Departments_Employees_HeadEmployeeId" FOREIGN KEY ("HeadEmployeeId") REFERENCES "Employees" ("Id") ON DELETE RESTRICT;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN

    CREATE OR REPLACE FUNCTION itam_auditlogs_immutable() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'AuditLogs is append-only (operation % is not allowed)', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_auditlogs_no_update BEFORE UPDATE OR DELETE ON "AuditLogs" FOR EACH ROW EXECUTE FUNCTION itam_auditlogs_immutable();
    CREATE TRIGGER trg_auditlogs_no_truncate BEFORE TRUNCATE ON "AuditLogs" FOR EACH STATEMENT EXECUTE FUNCTION itam_auditlogs_immutable();

    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261003220722_InitialCreate') THEN
    INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
    VALUES ('20261003220722_InitialCreate', '10.0.12');
    END IF;
END $EF$;
COMMIT;

START TRANSACTION;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE TABLE "AgentDevices" (
        "Id" uuid NOT NULL,
        "OrganizationId" uuid NOT NULL,
        "MachineId" character varying(64) NOT NULL,
        "TokenHash" character varying(128) NOT NULL,
        "Status" integer NOT NULL,
        "AssetId" uuid,
        "Hostname" character varying(128) NOT NULL,
        "Domain" character varying(256),
        "Manufacturer" character varying(256),
        "Model" character varying(256),
        "SerialNumber" character varying(256),
        "HardwareUuid" character varying(256),
        "FormFactor" character varying(64),
        "OsName" character varying(256),
        "OsVersion" character varying(64),
        "OsBuild" character varying(64),
        "OsArchitecture" character varying(64),
        "OsInstallDate" timestamp with time zone,
        "LastBootAt" timestamp with time zone,
        "Cpu" character varying(256),
        "CpuCores" integer,
        "RamMb" integer,
        "StorageGb" integer,
        "IpAddress" character varying(64),
        "MacAddress" character varying(64),
        "BiosVersion" character varying(64),
        "CurrentUser" character varying(256),
        "CurrentEmployeeId" uuid,
        "Antivirus" character varying(256),
        "AgentVersion" character varying(64),
        "Data" jsonb,
        "SoftwareCount" integer NOT NULL,
        "RegisteredAt" timestamp with time zone NOT NULL,
        "LastSeenAt" timestamp with time zone,
        "LastIp" character varying(64),
        "Comment" text,
        CONSTRAINT "PK_AgentDevices" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_AgentDevices_Assets_AssetId" FOREIGN KEY ("AssetId") REFERENCES "Assets" ("Id") ON DELETE SET NULL,
        CONSTRAINT "FK_AgentDevices_Employees_CurrentEmployeeId" FOREIGN KEY ("CurrentEmployeeId") REFERENCES "Employees" ("Id") ON DELETE SET NULL
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE TABLE "DiscoveredSoftware" (
        "Id" uuid NOT NULL,
        "DeviceId" uuid NOT NULL,
        "Name" character varying(512) NOT NULL,
        "Version" character varying(128),
        "Publisher" character varying(256),
        "InstallDate" date,
        CONSTRAINT "PK_DiscoveredSoftware" PRIMARY KEY ("Id"),
        CONSTRAINT "FK_DiscoveredSoftware_AgentDevices_DeviceId" FOREIGN KEY ("DeviceId") REFERENCES "AgentDevices" ("Id") ON DELETE CASCADE
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_AgentDevices_AssetId" ON "AgentDevices" ("AssetId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_AgentDevices_CurrentEmployeeId" ON "AgentDevices" ("CurrentEmployeeId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_AgentDevices_Hostname" ON "AgentDevices" USING gin ("Hostname" gin_trgm_ops);
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE UNIQUE INDEX "IX_AgentDevices_OrganizationId_MachineId" ON "AgentDevices" ("OrganizationId", "MachineId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_AgentDevices_SerialNumber" ON "AgentDevices" ("SerialNumber");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE UNIQUE INDEX "IX_AgentDevices_TokenHash" ON "AgentDevices" ("TokenHash");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_DiscoveredSoftware_DeviceId" ON "DiscoveredSoftware" ("DeviceId");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    CREATE INDEX "IX_DiscoveredSoftware_Name" ON "DiscoveredSoftware" ("Name");
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20261009061338_AgentInventory') THEN
    INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
    VALUES ('20261009061338_AgentInventory', '10.0.12');
    END IF;
END $EF$;
COMMIT;

