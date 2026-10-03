using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc.Testing;
using Npgsql;

namespace ITAM.IntegrationTests;

/// <summary>
/// Starts the real server (in-memory TestServer) against a throw-away PostgreSQL database.
/// Server: env ITAM_TEST_PG (default Host=localhost;Username=postgres;Password=postgres).
/// </summary>
public sealed class ItamFactory : WebApplicationFactory<ITAM.Api.Program>, IAsyncLifetime
{
    public const string AdminUser = "admin";
    public const string AdminPassword = "Admin12345!";
    private readonly string _server = Environment.GetEnvironmentVariable("ITAM_TEST_PG") ?? "Host=localhost;Port=5432;Username=postgres;Password=postgres";
    private readonly string _dbName = "itam_test_" + Guid.NewGuid().ToString("N")[..12];
    private readonly string _dataRoot = Path.Combine(Path.GetTempPath(), "itam-tests", Guid.NewGuid().ToString("N"));

    public string ConnectionString => new NpgsqlConnectionStringBuilder(_server) { Database = _dbName, MaxPoolSize = 50 }.ConnectionString;

    public async Task InitializeAsync()
    {
        await using (var c = new NpgsqlConnection(new NpgsqlConnectionStringBuilder(_server) { Database = "postgres" }.ConnectionString))
        {
            await c.OpenAsync();
            await using var cmd = new NpgsqlCommand($"CREATE DATABASE \"{_dbName}\"", c);
            await cmd.ExecuteNonQueryAsync();
        }
        // Configuration is read while the host is being built, so it is passed via environment variables.
        Environment.SetEnvironmentVariable("ITAM_DATA_ROOT", _dataRoot);
        Environment.SetEnvironmentVariable("ITAM_ConnectionStrings__Default", ConnectionString);
        Environment.SetEnvironmentVariable("ITAM_Itam__EnableJobs", "false");
        Environment.SetEnvironmentVariable("ITAM_Security__LoginRateLimitPerMinute", "10000");
        Environment.SetEnvironmentVariable("ITAM_Serilog__MinimumLevel__Default", "Warning");
        _ = Server; // start host → migrations + seed

        using var anon = CreateApiClient();
        var r = await anon.Http.PostAsJsonAsync("/api/setup/complete", new
        {
            organizationName = "Test Org", adminUserName = AdminUser, adminPassword = AdminPassword, adminDisplayName = "Администратор",
            timeZone = "Asia/Tashkent", language = "ru", currency = "UZS",
        });
        r.EnsureSuccessStatusCode();
    }

    public ApiClient CreateApiClient() => new(CreateDefaultClient(new Uri("http://localhost"), new CookieHandler()));

    public async Task<ApiClient> LoginAsync(string user = AdminUser, string password = AdminPassword)
    {
        var c = CreateApiClient();
        var r = await c.Http.PostAsJsonAsync("/api/auth/login", new { userName = user, password });
        if (!r.IsSuccessStatusCode) throw new InvalidOperationException($"login failed: {r.StatusCode} {await r.Content.ReadAsStringAsync()}");
        return c;
    }

    async Task IAsyncLifetime.DisposeAsync()
    {
        await base.DisposeAsync();
        NpgsqlConnection.ClearAllPools();
        await using var c = new NpgsqlConnection(new NpgsqlConnectionStringBuilder(_server) { Database = "postgres" }.ConnectionString);
        await c.OpenAsync();
        await using var cmd = new NpgsqlCommand($"DROP DATABASE IF EXISTS \"{_dbName}\" WITH (FORCE)", c);
        await cmd.ExecuteNonQueryAsync();
        try { Directory.Delete(_dataRoot, true); } catch { /* best effort */ }
    }
}

/// <summary>Keeps cookies (session + XSRF-TOKEN) and echoes the antiforgery token header like the SPA does.</summary>
public sealed class CookieHandler : DelegatingHandler
{
    private readonly CookieContainer _cookies = new();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var uri = request.RequestUri!;
        var header = _cookies.GetCookieHeader(uri);
        if (!string.IsNullOrEmpty(header)) request.Headers.Add("Cookie", header);
        var xsrf = _cookies.GetCookies(uri)["XSRF-TOKEN"]?.Value;
        if (xsrf is not null) request.Headers.Add("X-XSRF-TOKEN", xsrf);
        var response = await base.SendAsync(request, ct);
        if (response.Headers.TryGetValues("Set-Cookie", out var values))
            foreach (var v in values) _cookies.SetCookies(uri, v.Replace("samesite=strict", "", StringComparison.OrdinalIgnoreCase));
        return response;
    }
}

public sealed class ApiClient : IDisposable
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { Converters = { new JsonStringEnumConverter() } };
    public HttpClient Http { get; }
    public ApiClient(HttpClient http) => Http = http;

    public async Task<JsonNode> GetAsync(string url) => await Read(await Http.GetAsync(url));
    public async Task<JsonNode> PostAsync(string url, object? body = null) => await Read(await Http.PostAsJsonAsync(url, body ?? new { }, Json));
    public async Task<JsonNode> PutAsync(string url, object body) => await Read(await Http.PutAsJsonAsync(url, body, Json));
    public Task<HttpResponseMessage> RawPostAsync(string url, object? body = null) => Http.PostAsJsonAsync(url, body ?? new { }, Json);

    private static async Task<JsonNode> Read(HttpResponseMessage r)
    {
        var text = await r.Content.ReadAsStringAsync();
        if (!r.IsSuccessStatusCode) throw new ApiException(r.StatusCode, text);
        return string.IsNullOrEmpty(text) ? new JsonObject() : JsonNode.Parse(text)!;
    }

    public void Dispose() => Http.Dispose();
}

public sealed class ApiException : Exception
{
    public HttpStatusCode Status { get; }
    public string Body { get; }
    public string? Code => JsonNode.Parse(Body)?["error"]?["code"]?.GetValue<string>();
    public ApiException(HttpStatusCode status, string body) : base($"{(int)status}: {body}") { Status = status; Body = body; }
}

[CollectionDefinition(Name)]
public sealed class ItamCollection : ICollectionFixture<ItamFactory>
{
    public const string Name = "itam";
}
