using ITAM.Application.Admin;
using ITAM.Application.Common;
using ITAM.Infrastructure.Backups;
using ITAM.Infrastructure.Codes;
using ITAM.Infrastructure.Documents;
using ITAM.Infrastructure.Identity;
using ITAM.Infrastructure.Jobs;
using ITAM.Infrastructure.Notifications;
using ITAM.Infrastructure.Persistence;
using ITAM.Infrastructure.Reports;
using ITAM.Infrastructure.Storage;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace ITAM.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(this IServiceCollection services, IConfiguration config, string dataRoot, bool enableJobs = true)
    {
        var connectionString = config.GetConnectionString("Default")
                               ?? throw new InvalidOperationException("ConnectionStrings:Default is not configured");
        services.Configure<ItamPaths>(p =>
        {
            p.DataRoot = dataRoot;
            p.ConnectionString = connectionString;
            p.PgBinPath = config["Backup:PgBinPath"];
        });

        services.AddDbContext<AppDbContext>(o =>
        {
            o.UseNpgsql(connectionString, npg =>
            {
                npg.MigrationsAssembly(typeof(AppDbContext).Assembly.FullName);
                npg.CommandTimeout(120);
            });
            o.ConfigureWarnings(w => w.Ignore(Microsoft.EntityFrameworkCore.Diagnostics.CoreEventId.PossibleIncorrectRequiredNavigationWithQueryFilterInteractionWarning,
                Microsoft.EntityFrameworkCore.Diagnostics.CoreEventId.FirstWithoutOrderByAndFilterWarning));
        });
        services.AddScoped<IAppDbContext>(sp => sp.GetRequiredService<AppDbContext>());
        services.AddScoped<ITenantContext, DefaultTenantContext>();
        services.AddScoped<INumberGenerator, NumberGenerator>();
        services.AddScoped<DataSeeder>();

        var storageRoot = config["Storage:LocalPath"] is { Length: > 0 } sp ? sp : Path.Combine(dataRoot, "storage");
        services.AddSingleton<IFileStorage>(_ => new LocalFileStorage(storageRoot));
        services.AddSingleton<IBackupLocation>(new BackupLocation(config["Backup:Directory"] is { Length: > 0 } bd ? bd : Path.Combine(dataRoot, "backups")));

        var keysDir = new DirectoryInfo(Path.Combine(dataRoot, "keys"));
        keysDir.Create();
        services.AddDataProtection().SetApplicationName("ITAM").PersistKeysToFileSystem(keysDir);

        services.AddSingleton<Application.Common.IPasswordHasher, IdentityPasswordHasher>();
        services.AddSingleton<ISecretProtector, DataProtectionSecretProtector>();
        services.AddSingleton<IDocumentRenderer, DocxTemplateRenderer>();
        services.AddScoped<IPdfConverter, PdfConverter>();
        services.AddSingleton<ITabularExporter, TabularExporter>();
        services.AddSingleton<ITableReader, TableReader>();
        services.AddSingleton<ICodeGenerator, CodeGenerator>();
        services.AddScoped<IBackupEngine, PgBackupEngine>();
        services.AddHttpClient("telegram", c => c.Timeout = TimeSpan.FromSeconds(15));
        services.AddScoped<INotificationChannel, EmailChannel>();
        services.AddScoped<INotificationChannel, TelegramChannel>();

        if (enableJobs)
        {
            services.AddHostedService<NotificationJob>();
            services.AddHostedService<BackupSchedulerJob>();
            services.AddHostedService<MaintenanceJob>();
        }
        return services;
    }

    private sealed class BackupLocation(string dir) : IBackupLocation
    {
        public string DefaultDirectory => dir;
    }
}
