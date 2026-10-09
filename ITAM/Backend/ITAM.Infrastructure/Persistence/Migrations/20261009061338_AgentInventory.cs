using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace ITAM.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AgentInventory : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "AgentDevices",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uuid", nullable: false),
                    MachineId = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    TokenHash = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    AssetId = table.Column<Guid>(type: "uuid", nullable: true),
                    Hostname = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Domain = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    Manufacturer = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    Model = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    SerialNumber = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    HardwareUuid = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    FormFactor = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    OsName = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    OsVersion = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    OsBuild = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    OsArchitecture = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    OsInstallDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastBootAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    Cpu = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CpuCores = table.Column<int>(type: "integer", nullable: true),
                    RamMb = table.Column<int>(type: "integer", nullable: true),
                    StorageGb = table.Column<int>(type: "integer", nullable: true),
                    IpAddress = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    MacAddress = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    BiosVersion = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    CurrentUser = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    CurrentEmployeeId = table.Column<Guid>(type: "uuid", nullable: true),
                    Antivirus = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    AgentVersion = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    Data = table.Column<string>(type: "jsonb", nullable: true),
                    SoftwareCount = table.Column<int>(type: "integer", nullable: false),
                    RegisteredAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    LastSeenAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastIp = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    Comment = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AgentDevices", x => x.Id);
                    table.ForeignKey(
                        name: "FK_AgentDevices_Assets_AssetId",
                        column: x => x.AssetId,
                        principalTable: "Assets",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_AgentDevices_Employees_CurrentEmployeeId",
                        column: x => x.CurrentEmployeeId,
                        principalTable: "Employees",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "DiscoveredSoftware",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    DeviceId = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    Version = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    Publisher = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    InstallDate = table.Column<DateOnly>(type: "date", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DiscoveredSoftware", x => x.Id);
                    table.ForeignKey(
                        name: "FK_DiscoveredSoftware_AgentDevices_DeviceId",
                        column: x => x.DeviceId,
                        principalTable: "AgentDevices",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_AssetId",
                table: "AgentDevices",
                column: "AssetId");

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_CurrentEmployeeId",
                table: "AgentDevices",
                column: "CurrentEmployeeId");

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_Hostname",
                table: "AgentDevices",
                column: "Hostname")
                .Annotation("Npgsql:IndexMethod", "gin")
                .Annotation("Npgsql:IndexOperators", new[] { "gin_trgm_ops" });

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_OrganizationId_MachineId",
                table: "AgentDevices",
                columns: new[] { "OrganizationId", "MachineId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_SerialNumber",
                table: "AgentDevices",
                column: "SerialNumber");

            migrationBuilder.CreateIndex(
                name: "IX_AgentDevices_TokenHash",
                table: "AgentDevices",
                column: "TokenHash",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DiscoveredSoftware_DeviceId",
                table: "DiscoveredSoftware",
                column: "DeviceId");

            migrationBuilder.CreateIndex(
                name: "IX_DiscoveredSoftware_Name",
                table: "DiscoveredSoftware",
                column: "Name");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "DiscoveredSoftware");

            migrationBuilder.DropTable(
                name: "AgentDevices");
        }
    }
}
