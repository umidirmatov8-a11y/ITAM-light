using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;
using ITAM.Api.Auth;
using ITAM.Api.Middleware;
using ITAM.Application;
using ITAM.Application.Common;
using ITAM.Infrastructure;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.OpenApi;
using Serilog;
using Serilog.Events;

namespace ITAM.Api.Hosting;

public static class ItamHost
{
    public const string ServiceName = "ITAM";

    /// <summary>Runtime data root: config "Itam:DataRoot" / ITAM_DATA_ROOT → %ProgramData%\ITAM (service or installed config) → {app}/data.</summary>
    public static string ResolveDataRoot(IConfiguration config)
    {
        var configured = config["Itam:DataRoot"] ?? Environment.GetEnvironmentVariable("ITAM_DATA_ROOT");
        if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
        if (OperatingSystem.IsWindows())
        {
            // Installed layout: the service and the CLI (run from a console by an administrator) share %ProgramData%\ITAM.
            var programData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ITAM");
            if (WindowsServiceHelpers.IsWindowsService() || File.Exists(ConfigFilePath(programData))) return programData;
        }
        return Path.Combine(AppContext.BaseDirectory, "data");
    }

    public static string ConfigFilePath(string dataRoot) => Path.Combine(dataRoot, "config", "itam.json");

    public static void AddItamConfiguration(IConfigurationManager config, string[] args)
    {
        var dataRoot = ResolveDataRoot(config);
        config.AddJsonFile(ConfigFilePath(dataRoot), optional: true, reloadOnChange: false);
        config.AddEnvironmentVariables("ITAM_");
        config.AddCommandLine(args);
        config["Itam:ResolvedDataRoot"] = ResolveDataRoot(config);
    }

    public static WebApplication Build(string[] args, Action<WebApplicationBuilder>? configure = null)
    {
        var options = new WebApplicationOptions
        {
            Args = args,
            ContentRootPath = AppContext.BaseDirectory,
        };
        var builder = WebApplication.CreateBuilder(options);
        AddItamConfiguration(builder.Configuration, args);
        configure?.Invoke(builder);
        var config = builder.Configuration;
        var dataRoot = config["Itam:ResolvedDataRoot"]!;
        Directory.CreateDirectory(dataRoot);
        Directory.CreateDirectory(Path.Combine(dataRoot, "logs"));

        builder.Host.UseWindowsService(o => o.ServiceName = ServiceName);
        builder.Host.UseSerilog((ctx, lc) => lc
            .ReadFrom.Configuration(ctx.Configuration)
            .MinimumLevel.Override("Microsoft.AspNetCore.Hosting", LogEventLevel.Warning)
            .Enrich.FromLogContext()
            .WriteTo.Console()
            .WriteTo.File(Path.Combine(dataRoot, "logs", "itam-.log"), rollingInterval: RollingInterval.Day, retainedFileCountLimit: 30,
                outputTemplate: "{Timestamp:yyyy-MM-dd HH:mm:ss.fff zzz} [{Level:u3}] {SourceContext}: {Message:lj}{NewLine}{Exception}"));

        var urls = config["Server:Urls"];
        if (!string.IsNullOrWhiteSpace(urls) && string.IsNullOrEmpty(config["urls"]) && string.IsNullOrEmpty(Environment.GetEnvironmentVariable("ASPNETCORE_URLS")))
            builder.WebHost.UseUrls(urls.Split(';', StringSplitOptions.RemoveEmptyEntries));
        var certPath = config["Server:HttpsCertificatePath"];
        if (!string.IsNullOrWhiteSpace(certPath) && File.Exists(certPath))
            builder.WebHost.ConfigureKestrel(k => k.ConfigureHttpsDefaults(h =>
                h.ServerCertificate = X509CertificateLoader.LoadPkcs12FromFile(certPath, config["Server:HttpsCertificatePassword"])));
        builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = 200L * 1024 * 1024);

        ConfigureServices(builder.Services, config, dataRoot);
        var app = builder.Build();
        Configure(app, config);
        return app;
    }

    public static void ConfigureServices(IServiceCollection services, IConfiguration config, string dataRoot)
    {
        services.AddHttpContextAccessor();
        services.AddApplication();
        services.AddInfrastructure(config, dataRoot, enableJobs: config.GetValue("Itam:EnableJobs", true));
        services.AddScoped<ICurrentUser, HttpCurrentUser>();
        services.AddSingleton<SessionCookieService>();
        services.AddHostedService<DatabaseInitializer>();

        services.AddAuthentication(SessionAuthenticationHandler.Scheme)
            .AddScheme<SessionAuthenticationOptions, SessionAuthenticationHandler>(SessionAuthenticationHandler.Scheme, o =>
                o.SecureCookies = config.GetValue("Security:RequireHttpsCookies", false));
        services.AddSingleton<IAuthorizationPolicyProvider, PermissionPolicyProvider>();
        services.AddSingleton<IAuthorizationHandler, PermissionHandler>();
        services.AddAuthorization(o => o.FallbackPolicy = null);

        services.AddAntiforgery(o =>
        {
            o.HeaderName = "X-XSRF-TOKEN";
            o.Cookie.Name = "itam.af";
            o.Cookie.HttpOnly = true;
            o.Cookie.SameSite = SameSiteMode.Strict;
            o.Cookie.SecurePolicy = CookieSecurePolicy.SameAsRequest;
        });

        var loginLimit = config.GetValue("Security:LoginRateLimitPerMinute", 10);
        var apiLimit = config.GetValue("Security:ApiRateLimitPerMinute", 1200);
        services.AddRateLimiter(o =>
        {
            o.RejectionStatusCode = 429;
            o.OnRejected = async (ctx, ct) =>
            {
                ctx.HttpContext.Response.ContentType = "application/json; charset=utf-8";
                await ctx.HttpContext.Response.WriteAsync("{\"success\":false,\"error\":{\"code\":\"RATE_LIMITED\",\"message\":\"Слишком много запросов. Повторите позже.\"}}", ct);
            };
            o.AddPolicy("login", ctx => RateLimitPartition.GetFixedWindowLimiter(ctx.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                _ => new FixedWindowRateLimiterOptions { PermitLimit = loginLimit, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
            o.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(ctx =>
                ctx.Request.Path.StartsWithSegments("/api")
                    ? RateLimitPartition.GetFixedWindowLimiter(ctx.User.Identity?.Name ?? ctx.Connection.RemoteIpAddress?.ToString() ?? "anon",
                        _ => new FixedWindowRateLimiterOptions { PermitLimit = apiLimit, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 })
                    : RateLimitPartition.GetNoLimiter("static"));
        });

        services.Configure<ForwardedHeadersOptions>(o =>
        {
            o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto | ForwardedHeaders.XForwardedHost;
            o.KnownIPNetworks.Clear();
            o.KnownProxies.Clear();
        });

        services.AddControllers(o => o.Filters.Add(new ProducesAttribute("application/json")))
            .AddJsonOptions(o =>
            {
                o.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
                o.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
                o.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.Never;
            })
            .ConfigureApiBehaviorOptions(o => o.InvalidModelStateResponseFactory = ctx =>
            {
                var errors = ctx.ModelState.Where(kv => kv.Value?.Errors.Count > 0)
                    .ToDictionary(kv => JsonNamingPolicy.CamelCase.ConvertName(kv.Key.Split('.').Last()), kv => kv.Value!.Errors.Select(e => string.IsNullOrEmpty(e.ErrorMessage) ? "Некорректное значение" : e.ErrorMessage).ToArray());
                return new UnprocessableEntityObjectResult(new ApiErrorEnvelope(false, new ApiErrorBody("VALIDATION_FAILED", "Проверьте заполнение полей", errors)));
            });

        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(c =>
        {
            c.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "ITAM Platform API",
                Version = "v1",
                Description = "REST API корпоративной системы учёта IT-активов. Аутентификация: cookie-сессия (POST /api/auth/login) " +
                              "или заголовок Authorization: Bearer itam_<token>. Для изменяющих запросов с cookie передавайте X-XSRF-TOKEN."
            });
            var xml = Path.Combine(AppContext.BaseDirectory, "ITAM.Server.xml");
            if (File.Exists(xml)) c.IncludeXmlComments(xml);
            c.CustomSchemaIds(t => t.FullName!.Replace("ITAM.Application.", "").Replace("+", "."));
            c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme { Type = SecuritySchemeType.Http, Scheme = "bearer", Description = "Personal API token (itam_...)" });
        });
    }

    public static void Configure(WebApplication app, IConfiguration config)
    {
        if (config.GetValue("Server:UseForwardedHeaders", true)) app.UseForwardedHeaders();
        app.UseMiddleware<SecurityHeadersMiddleware>();
        app.UseMiddleware<ErrorHandlingMiddleware>();
        if (config.GetValue("Security:UseHsts", false)) app.UseHsts();
        if (config.GetValue("Security:UseHttpsRedirection", false)) app.UseHttpsRedirection();
        app.UseSerilogRequestLogging(o =>
        {
            o.MessageTemplate = "HTTP {RequestMethod} {RequestPath} responded {StatusCode} in {Elapsed:0} ms";
            o.GetLevel = (ctx, _, ex) => ex is not null || ctx.Response.StatusCode >= 500 ? LogEventLevel.Error
                : ctx.Request.Path.StartsWithSegments("/api") ? LogEventLevel.Information : LogEventLevel.Debug;
        });

        app.UseDefaultFiles();
        app.UseStaticFiles(new StaticFileOptions
        {
            OnPrepareResponse = ctx =>
            {
                if (ctx.File.Name == "index.html") ctx.Context.Response.Headers.CacheControl = "no-cache";
                else if (ctx.Context.Request.Path.StartsWithSegments("/assets")) ctx.Context.Response.Headers.CacheControl = "public,max-age=31536000,immutable";
            }
        });

        if (config.GetValue("Server:EnableSwagger", true))
        {
            app.UseSwagger();
            app.UseSwaggerUI(c => { c.SwaggerEndpoint("/swagger/v1/swagger.json", "ITAM API v1"); c.DocumentTitle = "ITAM API"; });
        }

        app.UseRouting();
        app.UseRateLimiter();
        app.UseAuthentication();
        app.UseMiddleware<PasswordChangeMiddleware>();
        app.UseMiddleware<AntiforgeryMiddleware>();
        app.UseAuthorization();
        app.MapControllers();
        app.MapGet("/health", async (Infrastructure.Persistence.AppDbContext db, CancellationToken ct) =>
        {
            var ok = false;
            try { ok = await db.Database.CanConnectAsync(ct); } catch { /* reported below */ }
            return Results.Json(new { status = ok ? "Healthy" : "Degraded", database = ok, version = typeof(ItamHost).Assembly.GetName().Version?.ToString(3) },
                statusCode: ok ? 200 : 503);
        });
        // SPA fallback for client-side routes (/assets/{id}, /employees/...), never for API calls.
        app.MapFallback(async ctx =>
        {
            if (ctx.Request.Path.StartsWithSegments("/api") || ctx.Request.Path.StartsWithSegments("/swagger"))
            {
                ctx.Response.StatusCode = 404;
                ctx.Response.ContentType = "application/json; charset=utf-8";
                await ctx.Response.WriteAsync("{\"success\":false,\"error\":{\"code\":\"NOT_FOUND\",\"message\":\"Ресурс не найден\"}}");
                return;
            }
            var index = Path.Combine(app.Environment.WebRootPath ?? Path.Combine(AppContext.BaseDirectory, "wwwroot"), "index.html");
            if (File.Exists(index))
            {
                ctx.Response.ContentType = "text/html; charset=utf-8";
                ctx.Response.Headers.CacheControl = "no-cache";
                await ctx.Response.SendFileAsync(index);
            }
            else
            {
                ctx.Response.ContentType = "text/plain; charset=utf-8";
                await ctx.Response.WriteAsync("ITAM API is running. Web UI is not deployed (wwwroot/index.html not found). API: /swagger");
            }
        });
    }
}
