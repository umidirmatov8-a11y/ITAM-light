using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using ITAM.Application.Assets;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace ITAM.Application.Agents;

/// <summary>
/// Windows inventory agents: registration with the shared enrollment key, inventory intake, matching computers to assets
/// (serial number → host name), automatic asset creation and keeping hardware fields of linked assets up to date.
/// </summary>
public sealed class AgentService
{
    public const string TokenPrefix = "itamagent_";
    private static readonly string[] JunkSerials =
    {
        "to be filled by o.e.m.", "default string", "system serial number", "0", "00000000", "none", "n/a", "not specified",
        "not applicable", "chassis serial number", "123456789", "0123456789", "invalid", "oem", "unknown"
    };

    private readonly IAppDbContext _db;
    private readonly ISettingsService _settings;
    private readonly ISecretProtector _protector;
    private readonly IClock _clock;
    private readonly IRegionScope _scope;
    private readonly AssetService _assets;
    private readonly AssetTemporalStore _temporal;
    private readonly IAuditService _audit;
    private readonly ILogger<AgentService> _log;

    public AgentService(IAppDbContext db, ISettingsService settings, ISecretProtector protector, IClock clock, IRegionScope scope,
        AssetService assets, AssetTemporalStore temporal, IAuditService audit, ILogger<AgentService> log)
    {
        _db = db; _settings = settings; _protector = protector; _clock = clock; _scope = scope;
        _assets = assets; _temporal = temporal; _audit = audit; _log = log;
    }

    public static string HashToken(string token) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(token)));

    private static string NewSecret(int bytes) => Convert.ToBase64String(RandomNumberGenerator.GetBytes(bytes))
        .Replace("+", "").Replace("/", "").Replace("=", "");

    // ================================================================ settings

    /// <summary>Settings with the enrollment key in clear text (generated on first use).</summary>
    public async Task<AgentSettingsDto> GetSettingsAsync(CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var key = _protector.Unprotect(s.EnrollmentKeyProtected);
        if (string.IsNullOrEmpty(key))
        {
            key = NewSecret(18);
            s.EnrollmentKeyProtected = _protector.Protect(key);
            await _settings.SaveAsync(s, ct);
        }
        var general = await _settings.GetAsync<GeneralSettings>(ct);
        return new AgentSettingsDto
        {
            EnrollmentKey = key, ServerUrl = string.IsNullOrWhiteSpace(general.PublicBaseUrl) ? null : general.PublicBaseUrl.TrimEnd('/'), AutoCreateAssets = s.AutoCreateAssets, DefaultRegionId = s.DefaultRegionId, DefaultLocationId = s.DefaultLocationId,
            UpdateAssetFields = s.UpdateAssetFields, InventoryIntervalHours = s.InventoryIntervalHours, StaleAfterDays = s.StaleAfterDays,
        };
    }

    public async Task<AgentSettingsDto> SaveSettingsAsync(AgentSettingsDto input, CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        if (input.DefaultRegionId is { } r && !await _db.Regions.AnyAsync(x => x.Id == r, ct)) throw new NotFoundException("Регион", r);
        if (input.DefaultLocationId is { } l && !await _db.Locations.AnyAsync(x => x.Id == l, ct)) throw new NotFoundException("Локация", l);
        s.AutoCreateAssets = input.AutoCreateAssets;
        s.DefaultRegionId = input.DefaultRegionId;
        s.DefaultLocationId = input.DefaultLocationId;
        s.UpdateAssetFields = input.UpdateAssetFields;
        s.InventoryIntervalHours = Math.Clamp(input.InventoryIntervalHours, 1, 168);
        s.StaleAfterDays = Math.Clamp(input.StaleAfterDays, 1, 365);
        await _settings.SaveAsync(s, ct);
        _audit.Log("agents.settings", "Setting", null, "agent");
        await _db.SaveChangesAsync(ct);
        return await GetSettingsAsync(ct);
    }

    /// <summary>Issues a new enrollment key. Registered devices keep working (they use their own tokens).</summary>
    public async Task<AgentSettingsDto> RegenerateKeyAsync(CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        s.EnrollmentKeyProtected = _protector.Protect(NewSecret(18));
        await _settings.SaveAsync(s, ct);
        _audit.Log("agents.key.regenerate", "Setting", null, "agent");
        await _db.SaveChangesAsync(ct);
        return await GetSettingsAsync(ct);
    }

    // ================================================================ agent protocol

    public async Task<AgentRegisterResponse> RegisterAsync(AgentRegisterRequest req, string? ip, CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var key = _protector.Unprotect(s.EnrollmentKeyProtected);
        if (string.IsNullOrEmpty(key) || !CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(key), Encoding.UTF8.GetBytes(req.EnrollmentKey.Trim())))
            throw new ForbiddenException("Неверный ключ регистрации агента");

        var machineId = req.MachineId.Trim().ToLowerInvariant();
        var token = TokenPrefix + NewSecret(32);
        var device = await _db.AgentDevices.FirstOrDefaultAsync(d => d.MachineId == machineId, ct);
        if (device is null)
        {
            device = new AgentDevice { MachineId = machineId, Hostname = req.Hostname.Trim(), RegisteredAt = _clock.UtcNow, Status = AgentDeviceStatus.New };
            _db.AgentDevices.Add(device);
        }
        // Re-registration (agent reinstalled, token lost) keeps the device and its link, only the token is replaced.
        device.TokenHash = HashToken(token);
        device.Hostname = req.Hostname.Trim();
        device.AgentVersion = req.AgentVersion;
        device.LastIp = ip;
        _audit.Log("agent.register", nameof(AgentDevice), device.Id, device.Hostname);
        await _db.SaveChangesAsync(ct);
        _log.LogInformation("Agent registered: {Host} ({MachineId}) from {Ip}", device.Hostname, machineId, ip);
        return new AgentRegisterResponse(device.Id, token, s.InventoryIntervalHours);
    }

    public async Task<AgentDevice?> AuthenticateAsync(string? token, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(token) || !token.StartsWith(TokenPrefix, StringComparison.Ordinal)) return null;
        var hash = HashToken(token);
        return await _db.AgentDevices.FirstOrDefaultAsync(d => d.TokenHash == hash, ct);
    }

    public async Task<AgentInventoryResponse> SubmitInventoryAsync(AgentDevice device, AgentInventoryReport r, string? ip, CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var now = _clock.UtcNow;

        device.Hostname = Trim(r.Hostname, 128) ?? device.Hostname;
        device.Domain = Trim(r.Domain, 256);
        device.Manufacturer = Trim(r.Manufacturer, 256);
        device.Model = Trim(r.Model, 256);
        device.SerialNumber = CleanSerial(r.SerialNumber);
        device.HardwareUuid = Trim(r.HardwareUuid, 256);
        device.FormFactor = Trim(r.FormFactor, 64);
        device.OsName = Trim(r.OsName, 256);
        device.OsVersion = Trim(r.OsVersion, 64);
        device.OsBuild = Trim(r.OsBuild, 64);
        device.OsArchitecture = Trim(r.OsArchitecture, 64);
        device.OsInstallDate = r.OsInstallDate?.ToUniversalTime();
        device.LastBootAt = r.LastBootAt?.ToUniversalTime();
        device.Cpu = Trim(r.Cpu, 256);
        device.CpuCores = r.CpuCores;
        device.RamMb = r.RamMb;
        device.StorageGb = r.Disks.Count > 0 ? (int)Math.Round(r.Disks.Sum(d => d.SizeGb ?? 0)) : null;
        var primary = r.Network.FirstOrDefault(n => n.Gateway.Count > 0 && n.Ip.Count > 0) ?? r.Network.FirstOrDefault(n => n.Ip.Count > 0);
        device.IpAddress = Trim(primary?.Ip.FirstOrDefault(i => !i.Contains(':')) ?? primary?.Ip.FirstOrDefault(), 64);
        device.MacAddress = Trim(primary?.MacAddress, 64);
        device.BiosVersion = Trim(r.BiosVersion, 64);
        device.CurrentUser = Trim(r.CurrentUser, 256);
        device.Antivirus = Trim(r.Antivirus, 256);
        device.AgentVersion = Trim(r.AgentVersion, 64) ?? device.AgentVersion;
        device.Data = Json.Serialize(new { disks = r.Disks, volumes = r.Volumes, network = r.Network, monitors = r.Monitors, gpus = r.Gpus, printers = r.Printers });
        device.LastSeenAt = now;
        device.LastIp = ip;
        device.CurrentEmployeeId = await ResolveEmployeeAsync(device.CurrentUser, ct);

        // Installed software is replaced as a whole on every report.
        await _db.DiscoveredSoftware.Where(x => x.DeviceId == device.Id).ExecuteDeleteAsync(ct);
        var software = r.Software
            .Where(x => !string.IsNullOrWhiteSpace(x.Name))
            .GroupBy(x => (x.Name!.Trim(), x.Version?.Trim()))
            .Select(g => g.First())
            .Take(5000)
            .Select(x => new DiscoveredSoftware
            {
                DeviceId = device.Id, Name = Trim(x.Name, 512)!, Version = Trim(x.Version, 128), Publisher = Trim(x.Publisher, 256),
                InstallDate = ParseInstallDate(x.InstallDate),
            }).ToList();
        _db.DiscoveredSoftware.AddRange(software);
        device.SoftwareCount = software.Count;

        await _db.SaveChangesAsync(ct);

        // Link to an asset (once) and keep the asset's hardware data current.
        string? assetNumber = null;
        try
        {
            if (device.Status == AgentDeviceStatus.New && device.AssetId is null)
            {
                var match = await FindMatchingAssetAsync(device, ct);
                if (match is not null) await LinkInternalAsync(device, match, "автоматически", ct);
                else if (s.AutoCreateAssets && s.DefaultRegionId is not null) await CreateAssetInternalAsync(device, null, s.DefaultRegionId, s.DefaultLocationId, ct);
            }
            if (device.AssetId is { } assetId)
            {
                var asset = await _db.Assets.FirstOrDefaultAsync(a => a.Id == assetId, ct);
                if (asset is null) { device.AssetId = null; device.Status = AgentDeviceStatus.New; }
                else
                {
                    assetNumber = asset.InventoryNumber;
                    if (s.UpdateAssetFields) await SyncAssetAsync(device, asset, ct);
                }
                await _db.SaveChangesAsync(ct);
            }
        }
        catch (Exception ex) when (ex is BusinessException or DbUpdateException)
        {
            // The inventory itself is already stored; linking problems are shown on the device page and resolved by an administrator.
            _db.ResetChanges();
            var message = ex is BusinessException ? ex.Message : "Не удалось обновить актив (данные изменены параллельно) — повторится при следующем отчёте";
            await _db.AgentDevices.Where(x => x.Id == device.Id).ExecuteUpdateAsync(u => u.SetProperty(x => x.Comment, message), ct);
            _log.LogWarning("Agent {Host}: asset linking failed: {Error}", device.Hostname, ex.Message);
        }
        return new AgentInventoryResponse(device.Id, s.InventoryIntervalHours, now, assetNumber);
    }

    private async Task<Guid?> ResolveEmployeeAsync(string? user, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(user)) return null;
        var login = user.Contains('\\') ? user[(user.LastIndexOf('\\') + 1)..] : user.Contains('@') ? user[..user.IndexOf('@')] : user;
        login = login.Trim().ToLowerInvariant();
        if (login.Length == 0) return null;
        return await _db.Employees.Where(e => e.Login != null && e.Login.ToLower() == login)
            .OrderBy(e => e.TerminationDate != null).Select(e => (Guid?)e.Id).FirstOrDefaultAsync(ct);
    }

    private async Task<Asset?> FindMatchingAssetAsync(AgentDevice d, CancellationToken ct)
    {
        var linked = _db.AgentDevices.Where(x => x.AssetId != null && x.Id != d.Id).Select(x => x.AssetId);
        if (d.SerialNumber is { } serial)
        {
            var s = serial.ToLower();
            var bySerial = await _db.Assets.Where(a => a.SerialNumber != null && a.SerialNumber.ToLower() == s && !linked.Contains(a.Id))
                .OrderBy(a => a.CreatedAt).FirstOrDefaultAsync(ct);
            if (bySerial is not null) return bySerial;
        }
        var host = d.Hostname.ToLower();
        return await _db.Assets.Where(a => a.Hostname != null && a.Hostname.ToLower() == host && !linked.Contains(a.Id))
            .OrderBy(a => a.CreatedAt).FirstOrDefaultAsync(ct);
    }

    private async Task LinkInternalAsync(AgentDevice device, Asset asset, string how, CancellationToken ct)
    {
        if (await _db.AgentDevices.AnyAsync(x => x.AssetId == asset.Id && x.Id != device.Id, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Актив {asset.InventoryNumber} уже связан с другим компьютером");
        device.AssetId = asset.Id;
        device.Status = AgentDeviceStatus.Linked;
        device.Comment = null;
        _temporal.AddInfoEvent(asset.Id, AssetEventType.AgentInventory, _clock.UtcNow,
            $"Компьютер {device.Hostname} связан с активом ({how})", new { hostname = device.Hostname, serial = device.SerialNumber });
        await _db.SaveChangesAsync(ct);
    }

    private async Task<Guid> CreateAssetInternalAsync(AgentDevice d, Guid? typeId, Guid? regionId, Guid? locationId, CancellationToken ct)
    {
        var typeCode = d.FormFactor switch
        {
            "Laptop" or "Tablet" => "LPT",
            "AllInOne" => "AIO",
            "Server" => "SRV",
            _ => "PC",
        };
        var type = typeId is { } t
            ? await _db.AssetTypes.FirstOrDefaultAsync(x => x.Id == t, ct) ?? throw new NotFoundException("Тип актива", t)
            : await _db.AssetTypes.Where(x => !x.IsArchived && (x.Code == typeCode || x.Prefix == typeCode)).FirstOrDefaultAsync(ct)
              ?? await _db.AssetTypes.Where(x => !x.IsArchived && (x.Code == "PC" || x.Prefix == "PC")).FirstOrDefaultAsync(ct)
              ?? throw new BusinessException("AGENT_NO_ASSET_TYPE", "Не найден тип актива для компьютера — создайте актив вручную");
        var manufacturerId = await ManufacturerIdAsync(d.Manufacturer, true, ct);
        var name = string.Join(' ', new[] { NiceManufacturer(d.Manufacturer), d.Model }.Where(x => !string.IsNullOrWhiteSpace(x)));
        var input = new AssetInput
        {
            Name = string.IsNullOrWhiteSpace(name) ? d.Hostname : name,
            AssetTypeId = type.Id,
            ManufacturerId = manufacturerId,
            Model = d.Model,
            SerialNumber = d.SerialNumber,
            RegionId = regionId,
            LocationId = locationId,
            Hostname = d.Hostname,
            IpAddress = d.IpAddress,
            MacAddress = d.MacAddress,
            Notes = $"Создан автоматически по данным агента ITAM ({d.Hostname})",
            CustomFields = await HardwareCustomFieldsAsync(d, type.Id, null, ct),
        };
        var created = await _assets.CreateAsync(input, ct);
        var asset = await _db.Assets.FirstAsync(a => a.Id == created.Id, ct);
        await LinkInternalAsync(d, asset, "актив создан агентом", ct);
        return asset.Id;
    }

    /// <summary>Updates hardware fields of the linked asset; writes one timeline entry listing what changed.</summary>
    private async Task SyncAssetAsync(AgentDevice d, Asset a, CancellationToken ct)
    {
        var changes = new List<string>();
        void Set(string label, string? current, string? value, Action<string?> apply)
        {
            if (string.IsNullOrWhiteSpace(value) || string.Equals(current, value, StringComparison.Ordinal)) return;
            apply(value);
            changes.Add($"{label}: {current ?? "—"} → {value}");
        }
        Set("Имя компьютера", a.Hostname, d.Hostname, v => a.Hostname = v);
        Set("IP", a.IpAddress, d.IpAddress, v => a.IpAddress = v);
        Set("MAC", a.MacAddress, d.MacAddress, v => a.MacAddress = v);
        if (string.IsNullOrWhiteSpace(a.SerialNumber)) Set("Серийный номер", a.SerialNumber, d.SerialNumber, v => a.SerialNumber = v);
        if (string.IsNullOrWhiteSpace(a.Model)) Set("Модель", a.Model, d.Model, v => a.Model = v);
        if (a.ManufacturerId is null && await ManufacturerIdAsync(d.Manufacturer, true, ct) is { } m) { a.ManufacturerId = m; changes.Add($"Производитель: {NiceManufacturer(d.Manufacturer)}"); }

        var cf = await HardwareCustomFieldsAsync(d, a.AssetTypeId, a.CustomFields, ct);
        if (cf is not null)
        {
            var before = Json.ToDictionary(a.CustomFields) ?? new Dictionary<string, JsonElement>();
            foreach (var (k, v) in cf)
            {
                if (before.TryGetValue(k, out var old) && old.ToString() == v.ToString()) continue;
                changes.Add($"{k}: {(before.TryGetValue(k, out var o) ? o.ToString() : "—")} → {v}");
                before[k] = v;
            }
            a.CustomFields = Json.Serialize(before);
        }
        if (changes.Count == 0) return;
        a.UpdatedAt = _clock.UtcNow;
        _temporal.AddInfoEvent(a.Id, AssetEventType.AgentInventory, _clock.UtcNow, "Данные обновлены агентом: " + string.Join("; ", changes.Take(10)),
            new { hostname = d.Hostname, changes });
    }

    /// <summary>Values for the standard hardware custom fields (cpu, ram, storage, gpu, os) when the asset type defines them.</summary>
    private async Task<Dictionary<string, JsonElement>?> HardwareCustomFieldsAsync(AgentDevice d, Guid assetTypeId, string? existing, CancellationToken ct)
    {
        var defs = await _db.CustomFieldDefinitions.AsNoTracking()
            .Where(f => f.EntityType == CustomFieldEntity.Asset && !f.IsArchived && (f.AssetTypeId == null || f.AssetTypeId == assetTypeId)
                        && (f.Key == "cpu" || f.Key == "ram" || f.Key == "storage" || f.Key == "gpu" || f.Key == "os"))
            .ToListAsync(ct);
        if (defs.Count == 0) return null;
        var data = Json.Deserialize<JsonObject>(d.Data);
        var result = new Dictionary<string, JsonElement>();
        foreach (var f in defs)
        {
            object? value = f.Key switch
            {
                "cpu" => d.Cpu,
                "ram" => d.RamMb is { } mb ? (int)Math.Round(mb / 1024.0) : null,
                "storage" => DescribeStorage(data),
                "gpu" => data?["gpus"] is JsonArray g && g.Count > 0 ? string.Join(", ", g.Select(x => x?.ToString())) : null,
                "os" => OsOption(d.OsName, f.Options),
                _ => null,
            };
            if (value is null) continue;
            result[f.Key] = JsonSerializer.SerializeToElement(value);
        }
        return result.Count == 0 ? null : result;
    }

    private static string? DescribeStorage(JsonObject? data)
    {
        if (data?["disks"] is not JsonArray disks || disks.Count == 0) return null;
        return string.Join(" + ", disks.Select(x =>
        {
            var size = x?["sizeGb"]?.GetValue<double?>();
            var media = x?["mediaType"]?.ToString();
            return $"{(size is { } s ? (s >= 1000 ? $"{Math.Round(s / 1000.0, 1)} ТБ" : $"{Math.Round(s)} ГБ") : "?")}{(string.IsNullOrEmpty(media) ? "" : " " + media)}";
        }));
    }

    /// <summary>OS for a dropdown field: only values present in its option list are written ("Microsoft Windows 11 Pro" → "Windows 11 Pro").</summary>
    private static string? OsOption(string? os, string? optionsJson)
    {
        if (string.IsNullOrWhiteSpace(os)) return null;
        var name = os.Replace("Microsoft ", "", StringComparison.OrdinalIgnoreCase).Trim();
        var options = Json.Deserialize<List<string>>(optionsJson);
        if (options is null || options.Count == 0) return name;
        return options.FirstOrDefault(o => string.Equals(o, name, StringComparison.OrdinalIgnoreCase))
               ?? options.FirstOrDefault(o => name.StartsWith(o, StringComparison.OrdinalIgnoreCase));
    }

    private async Task<Guid?> ManufacturerIdAsync(string? name, bool create, CancellationToken ct)
    {
        var nice = NiceManufacturer(name);
        if (string.IsNullOrWhiteSpace(nice)) return null;
        var lower = nice.ToLower();
        var id = await _db.Manufacturers.Where(m => m.Name.ToLower() == lower).Select(m => (Guid?)m.Id).FirstOrDefaultAsync(ct);
        if (id is not null || !create) return id;
        var m = new Manufacturer { Name = nice };
        _db.Manufacturers.Add(m);
        await _db.SaveChangesAsync(ct);
        return m.Id;
    }

    /// <summary>"LENOVO" → "Lenovo", "Hewlett-Packard" → "HP", "Dell Inc." → "Dell" (vendor strings from SMBIOS are inconsistent).</summary>
    public static string? NiceManufacturer(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var s = raw.Trim();
        var lower = s.ToLowerInvariant();
        if (lower.Contains("hewlett") || lower == "hp") return "HP";
        if (lower.StartsWith("dell")) return "Dell";
        if (lower.StartsWith("lenovo")) return "Lenovo";
        if (lower.StartsWith("asus")) return "ASUS";
        if (lower.StartsWith("acer")) return "Acer";
        if (lower.StartsWith("micro-star") || lower == "msi") return "MSI";
        if (lower.StartsWith("gigabyte")) return "Gigabyte";
        if (lower.StartsWith("microsoft")) return "Microsoft";
        if (lower.StartsWith("apple")) return "Apple";
        if (lower.StartsWith("samsung")) return "Samsung";
        if (lower.StartsWith("huawei")) return "Huawei";
        if (lower.StartsWith("vmware")) return "VMware";
        if (lower is "system manufacturer" or "to be filled by o.e.m." or "default string") return null;
        return s.Length > 1 && s == s.ToUpperInvariant() ? char.ToUpperInvariant(s[0]) + s[1..].ToLowerInvariant() : s;
    }

    public static string? CleanSerial(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var s = raw.Trim();
        if (s.Length < 3 || JunkSerials.Contains(s.ToLowerInvariant()) || s.All(c => c == '0' || c == ' ' || c == '-')) return null;
        return s.Length > 256 ? s[..256] : s;
    }

    private static DateOnly? ParseInstallDate(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        s = s.Trim();
        if (s.Length == 8 && DateOnly.TryParseExact(s, "yyyyMMdd", out var d)) return d;
        return DateOnly.TryParse(s, System.Globalization.CultureInfo.InvariantCulture, out d) ? d : null;
    }

    private static string? Trim(string? s, int max)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        s = s.Trim();
        return s.Length > max ? s[..max] : s;
    }

    // ================================================================ administration

    private async Task<IQueryable<AgentDevice>> VisibleAsync(CancellationToken ct)
    {
        var q = _db.AgentDevices.AsNoTracking();
        if (!_scope.IsUnrestricted)
        {
            // Unlinked computers are visible to everyone with agents.view; linked ones follow the asset's region.
            var allowed = _scope.Allowed.ToList();
            q = q.Where(d => d.AssetId == null || allowed.Contains(d.Asset!.RegionId));
        }
        await Task.CompletedTask;
        return q;
    }

    public async Task<PagedResult<AgentDeviceListItem>> ListAsync(AgentDeviceQuery q, CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var staleBefore = _clock.UtcNow.AddDays(-s.StaleAfterDays);
        var query = await VisibleAsync(ct);
        if (q.Status is { } st) query = query.Where(d => d.Status == st);
        if (q.Stale == true) query = query.Where(d => d.LastSeenAt == null || d.LastSeenAt < staleBefore);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var p = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(d => EF.Functions.ILike(d.Hostname, p) || (d.SerialNumber != null && EF.Functions.ILike(d.SerialNumber, p))
                                     || (d.CurrentUser != null && EF.Functions.ILike(d.CurrentUser, p)) || (d.Model != null && EF.Functions.ILike(d.Model, p))
                                     || (d.IpAddress != null && EF.Functions.ILike(d.IpAddress, p))
                                     || (d.Asset != null && EF.Functions.ILike(d.Asset.InventoryNumber, p)));
        }
        var sorts = new Dictionary<string, System.Linq.Expressions.Expression<Func<AgentDevice, object?>>>
        {
            ["hostname"] = d => d.Hostname, ["lastSeenAt"] = d => d.LastSeenAt, ["registeredAt"] = d => d.RegisteredAt,
            ["model"] = d => d.Model, ["osName"] = d => d.OsName, ["currentUser"] = d => d.CurrentUser, ["status"] = d => d.Status,
        };
        var employees = _db.Employees;
        return await query.SortBy(q, sorts, "hostname").ToPagedAsync(q, d => new AgentDeviceListItem(
            d.Id, d.Hostname, d.Domain, d.Status, d.AssetId, d.Asset != null ? d.Asset.InventoryNumber : null, d.Asset != null ? d.Asset.Name : null,
            d.Manufacturer, d.Model, d.SerialNumber, d.FormFactor, d.OsName, d.CurrentUser, d.CurrentEmployeeId,
            employees.Where(e => e.Id == d.CurrentEmployeeId).Select(e => e.FullName).FirstOrDefault(),
            d.IpAddress, d.AgentVersion, d.RegisteredAt, d.LastSeenAt, d.LastSeenAt == null || d.LastSeenAt < staleBefore, d.SoftwareCount), ct);
    }

    public async Task<AgentSummaryDto> SummaryAsync(CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var staleBefore = _clock.UtcNow.AddDays(-s.StaleAfterDays);
        var dayAgo = _clock.UtcNow.AddDays(-1);
        var q = await VisibleAsync(ct);
        var rows = await q.Select(d => new { d.Status, d.LastSeenAt, d.AgentVersion }).ToListAsync(ct);
        return new AgentSummaryDto(rows.Count, rows.Count(r => r.Status == AgentDeviceStatus.Linked), rows.Count(r => r.Status == AgentDeviceStatus.New),
            rows.Count(r => r.Status == AgentDeviceStatus.Ignored), rows.Count(r => r.LastSeenAt == null || r.LastSeenAt < staleBefore),
            rows.Count(r => r.LastSeenAt >= dayAgo),
            rows.Select(r => r.AgentVersion).Where(v => v != null).OrderByDescending(v => Version.TryParse(v, out var x) ? x : new Version()).FirstOrDefault());
    }

    public async Task<AgentDeviceDto> GetAsync(Guid id, CancellationToken ct)
    {
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var staleBefore = _clock.UtcNow.AddDays(-s.StaleAfterDays);
        var d = await (await VisibleAsync(ct)).Include(x => x.Asset).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        var currentName = d.CurrentEmployeeId is { } ce ? await _db.Employees.Where(e => e.Id == ce).Select(e => e.FullName).FirstOrDefaultAsync(ct) : null;
        var assetEmployeeName = d.Asset?.EmployeeId is { } ae ? await _db.Employees.Where(e => e.Id == ae).Select(e => e.FullName).FirstOrDefaultAsync(ct) : null;
        var mismatch = d.Asset?.EmployeeId is not null && d.CurrentEmployeeId is not null && d.Asset.EmployeeId != d.CurrentEmployeeId;
        return new AgentDeviceDto(d.Id, d.Hostname, d.Domain, d.Status, d.AssetId, d.Asset?.InventoryNumber, d.Asset?.Name, d.Asset?.EmployeeId, assetEmployeeName,
            d.Manufacturer, d.Model, d.SerialNumber, d.HardwareUuid, d.FormFactor, d.OsName, d.OsVersion, d.OsBuild, d.OsArchitecture, d.OsInstallDate, d.LastBootAt,
            d.Cpu, d.CpuCores, d.RamMb, d.StorageGb, d.IpAddress, d.MacAddress, d.BiosVersion, d.CurrentUser, d.CurrentEmployeeId, currentName, d.Antivirus,
            d.AgentVersion, Json.ToElement(d.Data), d.SoftwareCount, d.RegisteredAt, d.LastSeenAt, d.LastIp, d.LastSeenAt == null || d.LastSeenAt < staleBefore,
            d.Comment, mismatch);
    }

    public async Task<AgentDeviceDto?> ByAssetAsync(Guid assetId, CancellationToken ct)
    {
        var id = await _db.AgentDevices.Where(d => d.AssetId == assetId).Select(d => (Guid?)d.Id).FirstOrDefaultAsync(ct);
        return id is null ? null : await GetAsync(id.Value, ct);
    }

    public async Task<IReadOnlyList<DiscoveredSoftwareDto>> SoftwareAsync(Guid deviceId, CancellationToken ct)
    {
        await GetAsync(deviceId, ct); // visibility check
        return await _db.DiscoveredSoftware.AsNoTracking().Where(x => x.DeviceId == deviceId).OrderBy(x => x.Name)
            .Select(x => new DiscoveredSoftwareDto(x.Id, x.Name, x.Version, x.Publisher, x.InstallDate)).ToListAsync(ct);
    }

    public async Task<AgentDeviceDto> LinkAsync(Guid id, Guid assetId, CancellationToken ct)
    {
        var d = await _db.AgentDevices.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        var asset = await _assets.LoadVisibleAsync(assetId, ct);
        if (d.AssetId == asset.Id) return await GetAsync(id, ct);
        await LinkInternalAsync(d, asset, "вручную", ct);
        var s = await _settings.GetAsync<AgentSettings>(ct);
        if (s.UpdateAssetFields && d.LastSeenAt is not null) { await SyncAssetAsync(d, asset, ct); await _db.SaveChangesAsync(ct); }
        _audit.Log("agent.link", nameof(AgentDevice), d.Id, $"{d.Hostname} → {asset.InventoryNumber}");
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<AgentDeviceDto> UnlinkAsync(Guid id, CancellationToken ct)
    {
        var d = await _db.AgentDevices.Include(x => x.Asset).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        if (d.Asset is { } a)
        {
            _scope.EnsureAccess(a.RegionId);
            _temporal.AddInfoEvent(a.Id, AssetEventType.AgentInventory, _clock.UtcNow, $"Связь с компьютером {d.Hostname} удалена");
        }
        d.AssetId = null;
        d.Status = AgentDeviceStatus.Ignored; // otherwise automatic matching would link it again on the next report
        _audit.Log("agent.unlink", nameof(AgentDevice), d.Id, d.Hostname);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<AgentDeviceDto> CreateAssetAsync(Guid id, AgentCreateAssetRequest req, CancellationToken ct)
    {
        var d = await _db.AgentDevices.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        if (d.AssetId is not null) throw new ConflictException(ErrorCodes.Duplicate, "Компьютер уже связан с активом");
        var s = await _settings.GetAsync<AgentSettings>(ct);
        var region = req.RegionId ?? s.DefaultRegionId ?? throw new ValidationFailedException("Укажите регион",
            new Dictionary<string, string[]> { ["regionId"] = new[] { "Обязательное поле" } });
        await CreateAssetInternalAsync(d, req.AssetTypeId, region, req.LocationId ?? (req.RegionId is null ? s.DefaultLocationId : null), ct);
        _audit.Log("agent.create-asset", nameof(AgentDevice), d.Id, d.Hostname);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<AgentDeviceDto> SetIgnoredAsync(Guid id, bool ignored, CancellationToken ct)
    {
        var d = await _db.AgentDevices.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        if (ignored && d.AssetId is not null) throw new ConflictException(ErrorCodes.InvalidStatusTransition, "Сначала удалите связь с активом");
        d.Status = ignored ? AgentDeviceStatus.Ignored : (d.AssetId is null ? AgentDeviceStatus.New : AgentDeviceStatus.Linked);
        _audit.Log(ignored ? "agent.ignore" : "agent.unignore", nameof(AgentDevice), d.Id, d.Hostname);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    /// <summary>Removes the device and revokes its token (the agent must register again).</summary>
    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var d = await _db.AgentDevices.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Компьютер", id);
        await _db.DiscoveredSoftware.Where(x => x.DeviceId == id).ExecuteDeleteAsync(ct);
        _db.AgentDevices.Remove(d);
        _audit.Log("agent.delete", nameof(AgentDevice), d.Id, d.Hostname);
        await _db.SaveChangesAsync(ct);
    }

    /// <summary>Installed software across all visible computers, grouped by product name.</summary>
    public async Task<PagedResult<SoftwareSummaryItem>> SoftwareSummaryAsync(AgentSoftwareQuery q, CancellationToken ct)
    {
        var devices = (await VisibleAsync(ct)).Select(d => d.Id);
        var query = _db.DiscoveredSoftware.AsNoTracking().Where(x => devices.Contains(x.DeviceId));
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var p = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(x => EF.Functions.ILike(x.Name, p) || (x.Publisher != null && EF.Functions.ILike(x.Publisher, p)));
        }
        if (!string.IsNullOrWhiteSpace(q.Publisher)) query = query.Where(x => x.Publisher == q.Publisher);
        var grouped = query.GroupBy(x => x.Name).Select(g => new
        {
            Name = g.Key,
            Publisher = g.Max(x => x.Publisher),
            Devices = g.Select(x => x.DeviceId).Distinct().Count(),
            Versions = g.Select(x => x.Version).Distinct().Count(),
            Latest = g.Max(x => x.Version),
        });
        grouped = q.Sort switch
        {
            "name" => q.Desc ? grouped.OrderByDescending(x => x.Name) : grouped.OrderBy(x => x.Name),
            "publisher" => q.Desc ? grouped.OrderByDescending(x => x.Publisher) : grouped.OrderBy(x => x.Publisher),
            _ => grouped.OrderByDescending(x => x.Devices).ThenBy(x => x.Name),
        };
        var total = await grouped.CountAsync(ct);
        var items = await grouped.Skip((q.SafePage - 1) * q.SafePageSize).Take(q.SafePageSize).ToListAsync(ct);
        return new PagedResult<SoftwareSummaryItem>(items.Select(x => new SoftwareSummaryItem(x.Name, x.Publisher, x.Devices, x.Versions, x.Latest)).ToList(),
            total, q.SafePage, q.SafePageSize);
    }

    /// <summary>Computers having a given program installed.</summary>
    public async Task<IReadOnlyList<object>> SoftwareDevicesAsync(string name, CancellationToken ct)
    {
        var devices = await VisibleAsync(ct);
        return await _db.DiscoveredSoftware.AsNoTracking().Where(x => x.Name == name)
            .Join(devices, sw => sw.DeviceId, d => d.Id, (sw, d) => new
            {
                deviceId = d.Id, d.Hostname, d.CurrentUser, sw.Version, sw.InstallDate, d.AssetId,
                assetNumber = d.Asset != null ? d.Asset.InventoryNumber : null, d.LastSeenAt,
            })
            .OrderBy(x => x.Hostname).Cast<object>().ToListAsync(ct);
    }
}
