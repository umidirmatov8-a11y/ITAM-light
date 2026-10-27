using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace ITAM.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class SharedWarehouse : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "IsShared",
                table: "Locations",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            // Existing installations get a shared warehouse for incoming equipment in their first region
            // (an existing root warehouse named «Общий склад» is marked shared instead of creating a duplicate).
            migrationBuilder.Sql("""
                UPDATE "Locations" SET "IsShared" = TRUE
                WHERE "Name" = 'Общий склад' AND "ParentId" IS NULL AND "Type" = 6 AND NOT "IsArchived";

                INSERT INTO "Locations" ("Id", "OrganizationId", "Name", "Description", "Type", "RegionId", "IsShared", "FullPath", "SortOrder", "IsArchived", "CreatedAt")
                SELECT gen_random_uuid(), r."OrganizationId", 'Общий склад', 'Общий склад для прихода техники: доступен всем регионам', 6, r."Id", TRUE,
                       'Общий склад', 0, FALSE, now()
                FROM (SELECT DISTINCT ON ("OrganizationId") "Id", "OrganizationId" FROM "Regions" WHERE NOT "IsArchived"
                      ORDER BY "OrganizationId", "SortOrder", "Name") r
                WHERE NOT EXISTS (SELECT 1 FROM "Locations" l WHERE l."OrganizationId" = r."OrganizationId" AND l."IsShared");
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "IsShared",
                table: "Locations");
        }
    }
}
