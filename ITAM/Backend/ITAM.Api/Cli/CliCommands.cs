using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using ITAM.Api.Hosting;
using ITAM.Application.Admin;
using ITAM.Application.Common;
using ITAM.Application.Setup;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace ITAM.Api.Cli;

/// <summary>
/// Command line used by the installer and administrators:
///   ITAM.Server.exe setup --db-host localhost --db-port 5433 --db-user postgres --db-password *** [--db-name itam]
///                         [--app-db-user itam --app-db-password ***] --port 8080 --data-root C:\ProgramData\ITAM
///                         --admin-user admin --admin-password *** --org "Компания" [--timezone Asia/Tashkent] [--demo]
///   ITAM.Server.exe migrate | check | backup [--out dir] | restore &lt;file&gt; --yes | reset-admin --user admin --password *** | version
/// </summary>
public static partial class CliCommands
{
    private static readonly HashSet<string> Commands = new(StringComparer.OrdinalIgnoreCase)
        { "setup", "migrate", "check", "backup", "restore", "reset-admin", "version", "help", "--help", "/?" };

    public static bool IsCommand(string arg) => Commands.Contains(arg);

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_]{0,62}$")]
    private static partial Regex IdentifierRegex();

    private static Dictionary<string, string?> ParseOptions(string[] args)
    {
        var d = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        for (var i = 1; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--")) { d.TryAdd("_positional", args[i]); continue; }
            var key = args[i][2..];
            var value = i + 1 < args.Length && !args[i + 1].StartsWith("--") ? args[++i] : "true";
            d[key] = value;
        }
        return d;
    }

    public static async Task<int> RunAsync(string[] args)
    {
        var cmd = args[0].ToLowerInvariant();
        var o = ParseOptions(args);
        try
        {
            return cmd switch
            {
                "setup" => await SetupAsync(o),
                "migrate" => await WithServicesAsync(o, async sp => { await sp.GetRequiredService<DataSeeder>().MigrateAndSeedAsync(); Console.WriteLine("База данных обновлена."); return 0; }),
                "check" => await WithServicesAsync(o, async sp =>
                {
                    var ok = await sp.GetRequiredService<AppDbContext>().Database.CanConnectAsync();
                    Console.WriteLine(ok ? "Подключение к базе данных: OK" : "Нет подключения к базе данных");
                    return ok ? 0 : 2;
                }),
                "backup" => await WithServicesAsync(o, async sp =>
                {
                    var engine = sp.GetRequiredService<IBackupEngine>();
                    var dir = o.GetValueOrDefault("out") ?? await sp.GetRequiredService<BackupService>().DirectoryAsync(CancellationToken.None);
                    var (path, size, sha) = await engine.CreateAsync(dir, true);
                    Console.WriteLine($"Резервная копия: {path} ({size / 1024} КБ, SHA-256 {sha})");
                    return 0;
                }),
                "restore" => await WithServicesAsync(o, async sp =>
                {
                    var file = o.GetValueOrDefault("_positional") ?? o.GetValueOrDefault("file") ?? throw new ArgumentException("Укажите файл резервной копии");
                    if (o.GetValueOrDefault("yes") != "true") { Console.Error.WriteLine("Восстановление перезапишет текущие данные. Добавьте --yes для подтверждения."); return 3; }
                    await sp.GetRequiredService<IBackupEngine>().RestoreAsync(Path.GetFullPath(file));
                    await sp.GetRequiredService<DataSeeder>().MigrateAndSeedAsync();
                    Console.WriteLine("Данные восстановлены. Перезапустите службу ITAM.");
                    return 0;
                }),
                "reset-admin" => await WithServicesAsync(o, sp => ResetAdminAsync(sp, o)),
                "version" => PrintVersion(),
                _ => PrintHelp()
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("ОШИБКА: " + ex.Message);
            return 1;
        }
    }

    private static int PrintVersion()
    {
        Console.WriteLine("ITAM Platform " + typeof(CliCommands).Assembly.GetName().Version?.ToString(3));
        return 0;
    }

    private static int PrintHelp()
    {
        Console.WriteLine("""
            ITAM.Server.exe                         запуск веб-сервера (или Windows Service)
            ITAM.Server.exe setup [параметры]       первичная настройка (используется установщиком)
                --db-host --db-port --db-user --db-password [--db-name itam]
                [--app-db-user itam --app-db-password ***]  создать отдельного пользователя БД
                --port 8080 --data-root <каталог данных> --pg-bin <каталог bin PostgreSQL>
                --admin-user admin --admin-password *** --org "Организация" [--timezone Asia/Tashkent] [--demo]
            ITAM.Server.exe migrate                 применить миграции и справочные данные
            ITAM.Server.exe check                   проверить подключение к БД
            ITAM.Server.exe backup [--out <dir>]    создать резервную копию
            ITAM.Server.exe restore <file> --yes    восстановить из резервной копии
            ITAM.Server.exe reset-admin --user admin --password ***   сброс пароля администратора
            """);
        return 0;
    }

    private static IConfigurationRoot BuildConfiguration(Dictionary<string, string?> o)
    {
        var builder = new ConfigurationManager();
        builder.SetBasePath(AppContext.BaseDirectory);
        builder.AddJsonFile("appsettings.json", optional: true);
        if (o.TryGetValue("data-root", out var dr) && dr is not null) builder["Itam:DataRoot"] = dr;
        ItamHost.AddItamConfiguration(builder, Array.Empty<string>());
        builder["Itam:EnableJobs"] = "false";
        return builder;
    }

    private static async Task<int> WithServicesAsync(Dictionary<string, string?> o, Func<IServiceProvider, Task<int>> action)
    {
        var config = BuildConfiguration(o);
        var services = new ServiceCollection();
        services.AddLogging(l => l.AddSimpleConsole(c => c.SingleLine = true).SetMinimumLevel(LogLevel.Warning)
            .AddFilter("Microsoft.EntityFrameworkCore.Database.Command", LogLevel.Critical).AddFilter("Microsoft.AspNetCore.DataProtection", LogLevel.Error));
        services.AddSingleton<IConfiguration>(config);
        ItamHost.ConfigureServices(services, config, config["Itam:ResolvedDataRoot"]!);
        await using var root = services.BuildServiceProvider();
        await using var scope = root.CreateAsyncScope();
        scope.ServiceProvider.GetRequiredService<SystemContext>().Enabled = true;
        return await action(scope.ServiceProvider);
    }

    private static async Task<int> ResetAdminAsync(IServiceProvider sp, Dictionary<string, string?> o)
    {
        var userName = o.GetValueOrDefault("user") ?? "admin";
        var password = o.GetValueOrDefault("password") ?? throw new ArgumentException("Укажите --password");
        var db = sp.GetRequiredService<AppDbContext>();
        var hasher = sp.GetRequiredService<IPasswordHasher>();
        PasswordPolicyCheck(sp, password);
        var user = await db.Users.IgnoreQueryFilters().FirstOrDefaultAsync(u => u.NormalizedUserName == userName.ToUpperInvariant());
        var role = await db.Roles.FirstAsync(r => r.Code == BuiltInRoles.SuperAdmin);
        if (user is null)
        {
            user = new User { UserName = userName, NormalizedUserName = userName.ToUpperInvariant(), DisplayName = "Администратор", AllRegions = true };
            db.Users.Add(user);
        }
        user.IsDeleted = false;
        user.IsActive = true;
        user.PasswordHash = hasher.Hash(password);
        user.PasswordChangedAt = DateTime.UtcNow;
        user.MustChangePassword = o.GetValueOrDefault("must-change") == "true";
        user.FailedLoginCount = 0;
        user.LockoutEnd = null;
        user.AllRegions = true;
        if (!await db.UserRoles.AnyAsync(r => r.UserId == user.Id && r.RoleId == role.Id)) db.UserRoles.Add(new UserRole { UserId = user.Id, RoleId = role.Id });
        sp.GetRequiredService<IAuditService>().Log("cli.reset-admin", nameof(User), user.Id, user.UserName);
        await db.SaveChangesAsync();
        Console.WriteLine($"Пароль пользователя {userName} сброшен, роль суперадминистратора назначена.");
        return 0;
    }

    private static void PasswordPolicyCheck(IServiceProvider sp, string password)
    {
        var settings = sp.GetRequiredService<ISettingsService>().GetAsync<SecuritySettings>().GetAwaiter().GetResult();
        Application.Auth.PasswordPolicy.Ensure(password, settings);
    }

    private static async Task<int> SetupAsync(Dictionary<string, string?> o)
    {
        string Opt(string key, string? def = null) => o.GetValueOrDefault(key) ?? def ?? throw new ArgumentException($"Не указан параметр --{key}");
        var dataRoot = Path.GetFullPath(Opt("data-root", OperatingSystem.IsWindows()
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ITAM")
            : Path.Combine(AppContext.BaseDirectory, "data")));
        o["data-root"] = dataRoot;
        var port = int.Parse(Opt("port", "8080"));
        var dbName = Opt("db-name", "itam");
        if (!IdentifierRegex().IsMatch(dbName)) throw new ArgumentException("Недопустимое имя базы данных");

        var admin = new NpgsqlConnectionStringBuilder
        {
            Host = Opt("db-host", "localhost"), Port = int.Parse(Opt("db-port", "5432")), Username = Opt("db-user", "postgres"),
            Password = Opt("db-password", ""), Database = "postgres", Timeout = 15
        };
        Console.WriteLine($"Подключение к PostgreSQL {admin.Host}:{admin.Port} ...");
        await WaitForDatabaseAsync(admin.ConnectionString);

        var appUser = o.GetValueOrDefault("app-db-user");
        var appPassword = o.GetValueOrDefault("app-db-password");
        await using (var conn = new NpgsqlConnection(admin.ConnectionString))
        {
            await conn.OpenAsync();
            var owner = admin.Username!;
            if (!string.IsNullOrEmpty(appUser))
            {
                if (!IdentifierRegex().IsMatch(appUser)) throw new ArgumentException("Недопустимое имя пользователя БД");
                if (string.IsNullOrEmpty(appPassword)) throw new ArgumentException("Укажите --app-db-password");
                var exists = await Scalar(conn, "SELECT 1 FROM pg_roles WHERE rolname = @n", appUser) is not null;
                var pwd = appPassword.Replace("'", "''");
                await Exec(conn, exists ? $"ALTER ROLE \"{appUser}\" WITH LOGIN PASSWORD '{pwd}'" : $"CREATE ROLE \"{appUser}\" WITH LOGIN PASSWORD '{pwd}'");
                owner = appUser;
            }
            if (await Scalar(conn, "SELECT 1 FROM pg_database WHERE datname = @n", dbName) is null)
            {
                Console.WriteLine($"Создание базы данных {dbName} ...");
                await Exec(conn, $"CREATE DATABASE \"{dbName}\" OWNER \"{owner}\" ENCODING 'UTF8' TEMPLATE template0");
            }
            else if (!string.IsNullOrEmpty(appUser))
                await Exec(conn, $"ALTER DATABASE \"{dbName}\" OWNER TO \"{owner}\"");
        }
        if (!string.IsNullOrEmpty(appUser))
        {
            // pg_trgm must be created by a privileged role; the application role owns everything else.
            var su = new NpgsqlConnectionStringBuilder(admin.ConnectionString) { Database = dbName };
            await using var conn = new NpgsqlConnection(su.ConnectionString);
            await conn.OpenAsync();
            await Exec(conn, "CREATE EXTENSION IF NOT EXISTS pg_trgm");
            await Exec(conn, $"ALTER SCHEMA public OWNER TO \"{appUser}\"");
        }

        var appCs = new NpgsqlConnectionStringBuilder(admin.ConnectionString)
        {
            Database = dbName,
            Username = string.IsNullOrEmpty(appUser) ? admin.Username : appUser,
            Password = string.IsNullOrEmpty(appUser) ? admin.Password : appPassword,
            Timeout = 30, MaxPoolSize = 100
        };
        WriteConfig(dataRoot, appCs.ConnectionString, port, o.GetValueOrDefault("pg-bin"));
        Console.WriteLine($"Конфигурация записана: {ItamHost.ConfigFilePath(dataRoot)}");

        return await WithServicesAsync(o, async sp =>
        {
            Console.WriteLine("Применение миграций и справочных данных ...");
            await sp.GetRequiredService<DataSeeder>().MigrateAndSeedAsync();
            var setup = sp.GetRequiredService<SetupService>();
            var adminUser = o.GetValueOrDefault("admin-user") ?? "admin";
            if (!await setup.IsCompletedAsync(CancellationToken.None))
            {
                if (o.GetValueOrDefault("admin-password") is { Length: > 0 } adminPassword)
                {
                    await setup.CompleteAsync(new SetupRequest
                    {
                        OrganizationName = o.GetValueOrDefault("org") ?? "Организация",
                        AdminUserName = adminUser,
                        AdminPassword = adminPassword,
                        TimeZone = o.GetValueOrDefault("timezone") ?? "Asia/Tashkent",
                        Language = o.GetValueOrDefault("language") ?? "ru",
                        Currency = o.GetValueOrDefault("currency") ?? "UZS",
                        PublicBaseUrl = $"http://{LocalAddresses().FirstOrDefault() ?? "localhost"}:{port}",
                        LoadDemoData = o.GetValueOrDefault("demo") == "true",
                    }, CancellationToken.None);
                    Console.WriteLine($"Создан администратор: {adminUser}");
                }
                else Console.WriteLine("Администратор не создан — завершите настройку в мастере первого запуска в браузере.");
            }
            else if (o.GetValueOrDefault("reset-admin") == "true" && o.GetValueOrDefault("admin-password") is { Length: > 0 })
            {
                await ResetAdminAsync(sp, new Dictionary<string, string?> { ["user"] = adminUser, ["password"] = o["admin-password"] });
            }
            else Console.WriteLine("Существующая установка обнаружена — данные сохранены.");

            Console.WriteLine();
            Console.WriteLine("Установка завершена.");
            foreach (var ip in LocalAddresses().DefaultIfEmpty("localhost")) Console.WriteLine($"ITAM URL: http://{ip}:{port}");
            Console.WriteLine($"Administrator: {adminUser}");
            return 0;
        });
    }

    private static void WriteConfig(string dataRoot, string connectionString, int port, string? pgBin)
    {
        var path = ItamHost.ConfigFilePath(dataRoot);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var root = File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? new JsonObject() : new JsonObject();
        JsonObject Section(string name) => root[name] as JsonObject ?? (JsonObject)(root[name] = new JsonObject());
        Section("ConnectionStrings")["Default"] = connectionString;
        Section("Server")["Urls"] = $"http://0.0.0.0:{port}";
        Section("Itam")["DataRoot"] = dataRoot;
        if (!string.IsNullOrWhiteSpace(pgBin)) Section("Backup")["PgBinPath"] = pgBin;
        File.WriteAllText(path, root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    private static async Task WaitForDatabaseAsync(string cs)
    {
        Exception? last = null;
        for (var i = 0; i < 30; i++)
        {
            try
            {
                await using var conn = new NpgsqlConnection(cs);
                await conn.OpenAsync();
                return;
            }
            catch (Exception ex) when (ex is NpgsqlException or SocketException or TimeoutException)
            {
                if (ex is PostgresException { SqlState: "28P01" }) throw new InvalidOperationException("Неверный пароль пользователя PostgreSQL");
                last = ex;
                await Task.Delay(2000);
            }
        }
        throw new InvalidOperationException("PostgreSQL недоступен: " + last?.Message);
    }

    private static async Task<object?> Scalar(NpgsqlConnection conn, string sql, string param)
    {
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("n", param);
        return await cmd.ExecuteScalarAsync();
    }

    private static async Task Exec(NpgsqlConnection conn, string sql)
    {
        await using var cmd = new NpgsqlCommand(sql, conn);
        await cmd.ExecuteNonQueryAsync();
    }

    public static IEnumerable<string> LocalAddresses()
    {
        try
        {
            return NetworkInterface.GetAllNetworkInterfaces()
                .Where(n => n.OperationalStatus == OperationalStatus.Up && n.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                .Where(a => a.Address.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(a.Address))
                .Select(a => a.Address.ToString()).Distinct().ToList();
        }
        catch
        {
            return Array.Empty<string>();
        }
    }
}
