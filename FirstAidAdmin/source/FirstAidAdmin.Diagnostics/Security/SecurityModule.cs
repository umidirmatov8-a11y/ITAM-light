using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Security;

public sealed record DefenderStatus(bool Available, bool ServiceEnabled, bool AntivirusEnabled, bool RealTime, int SignatureAgeDays, bool? TamperProtected);
public sealed record FirewallProfile(string Name, bool Enabled);

/// <summary>Read-only security posture: Defender, third-party AV, firewall, UAC, signatures.</summary>
public sealed class SecurityModule : DiagnosticModuleBase
{
    public const string Script =
        "$d=$null;try{$m=Get-MpComputerStatus -ErrorAction Stop;$d=@{svc=$m.AMServiceEnabled;av=$m.AntivirusEnabled;rt=$m.RealTimeProtectionEnabled;age=$m.AntivirusSignatureAge;tamper=$m.IsTamperProtected}}catch{};" +
        "$av=@();try{$av=@(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop | Select displayName,productState)}catch{};" +
        "$fw=@(Get-NetFirewallProfile -ErrorAction SilentlyContinue | Select Name,@{n='Enabled';e={[bool]$_.Enabled}});" +
        "@{defender=$d;av=$av;fw=$fw} | ConvertTo-Json -Depth 3 -Compress";

    private readonly IPowerShellRunner _ps;
    private readonly IRegistryProbe _registry;

    public SecurityModule(IPowerShellRunner ps, IRegistryProbe registry)
    {
        _ps = ps;
        _registry = registry;
    }

    public override string Id => ModuleIds.Security;
    public override string Name => "Безопасность";
    public override DiagnosticCategory Category => DiagnosticCategory.Security;

    public static (DefenderStatus Defender, List<string> ThirdPartyAv, List<FirewallProfile> Firewall) Parse(JsonElement root)
    {
        var def = new DefenderStatus(false, false, false, false, -1, null);
        if (root.TryGetProperty("defender", out var d) && d.ValueKind == JsonValueKind.Object)
        {
            static bool B(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.True;
            def = new DefenderStatus(true, B(d, "svc"), B(d, "av"), B(d, "rt"),
                d.TryGetProperty("age", out var a) && a.TryGetInt32(out var age) ? age : -1,
                d.TryGetProperty("tamper", out var t) && t.ValueKind is JsonValueKind.True or JsonValueKind.False ? t.GetBoolean() : null);
        }
        static IEnumerable<JsonElement> Arr(JsonElement r, string n) => r.TryGetProperty(n, out var v) ? v.ValueKind == JsonValueKind.Array ? v.EnumerateArray() : v.ValueKind == JsonValueKind.Object ? new[] { v } : Array.Empty<JsonElement>() : Array.Empty<JsonElement>();
        var av = Arr(root, "av").Select(x => x.TryGetProperty("displayName", out var n) ? n.GetString() ?? "" : "")
            .Where(n => n.Length > 0 && !n.Contains("Defender", StringComparison.OrdinalIgnoreCase)).Distinct().ToList();
        var fw = Arr(root, "fw").Select(x => new FirewallProfile(x.TryGetProperty("Name", out var n) ? n.GetString() ?? "" : "",
            x.TryGetProperty("Enabled", out var e) && e.ValueKind == JsonValueKind.True)).ToList();
        return (def, av, fw);
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows) { root.Status = DiagnosticStatus.Skipped; root.Summary = "Доступно только в Windows"; return; }

        var json = await _ps.RunJsonAsync(Script, TimeSpan.FromSeconds(60), ct).ConfigureAwait(false);
        if (json is { } j)
        {
            var (def, av, fw) = Parse(j);
            var thirdParty = string.Join(", ", av);
            if (!def.Available)
            {
                Check(root, C.SecDefender, "Microsoft Defender", av.Count > 0 ? DiagnosticStatus.Info : DiagnosticStatus.Warning,
                    av.Count > 0 ? $"Defender неактивен; используется сторонний антивирус: {thirdParty}" : "Состояние Defender недоступно")
                    .WithEvidence("thirdParty", thirdParty);
            }
            else
            {
                var ok = def.RealTime && def.AntivirusEnabled;
                Check(root, C.SecDefender, "Microsoft Defender",
                        ok ? DiagnosticStatus.Ok : av.Count > 0 ? DiagnosticStatus.Info : DiagnosticStatus.Error,
                        ok ? $"Защита в реальном времени включена{(def.TamperProtected == true ? ", защита от подделки включена" : "")}"
                           : av.Count > 0 ? $"Defender в пассивном режиме, активен сторонний антивирус: {thirdParty}" : "Защита в реальном времени ОТКЛЮЧЕНА",
                        ok || av.Count > 0 ? null : Severity.Critical)
                    .WithEvidence("realTime", def.RealTime).WithEvidence("antivirusEnabled", def.AntivirusEnabled)
                    .WithEvidence("serviceEnabled", def.ServiceEnabled).WithEvidence("thirdParty", thirdParty)
                    .WithRecommendation(ok ? "" : "Включите защиту в «Безопасность Windows».", ok ? Array.Empty<string>() : new[] { A.OpenWindowsSecurity });

                if (def.AntivirusEnabled && def.SignatureAgeDays >= 0)
                    Check(root, C.SecSignatures, "Антивирусные базы",
                            def.SignatureAgeDays > 14 ? DiagnosticStatus.Error : def.SignatureAgeDays > 7 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                            $"Возраст сигнатур: {def.SignatureAgeDays} дн.")
                        .WithEvidence("ageDays", def.SignatureAgeDays)
                        .WithRecommendation(def.SignatureAgeDays > 7 ? "Обновите сигнатуры Defender." : "", def.SignatureAgeDays > 7 ? new[] { A.DefenderUpdateSignatures } : Array.Empty<string>());
            }
            Check(root, C.SecAntivirus, "Антивирусные продукты (Security Center)", DiagnosticStatus.Info,
                av.Count > 0 ? $"Сторонние: {thirdParty}" : "Сторонние антивирусы не зарегистрированы").WithEvidence("thirdParty", thirdParty);

            if (fw.Count > 0)
            {
                var off = fw.Where(p => !p.Enabled).ToList();
                var c = Check(root, C.SecFirewall, "Брандмауэр Windows", off.Count == 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                    off.Count == 0 ? "Включён для всех профилей" : $"Выключен для профилей: {string.Join(", ", off.Select(p => p.Name))}");
                foreach (var p in fw) c.WithEvidence(p.Name, p.Enabled ? "On" : "Off");
                if (off.Count > 0) c.WithRecommendation("Включите брандмауэр (если нет корпоративного межсетевого экрана на хосте).", A.OpenFirewall);
            }
        }
        else
        {
            Check(root, C.SecDefender, "Microsoft Defender", DiagnosticStatus.Warning, "Не удалось получить состояние защиты");
        }

        var lua = _registry.GetValue(RegistryHive.LocalMachine, @"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA");
        var consent = _registry.GetValue(RegistryHive.LocalMachine, @"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "ConsentPromptBehaviorAdmin");
        var luaOn = lua is null || Convert.ToInt32(lua) == 1;
        Check(root, C.SecUac, "Контроль учётных записей (UAC)", luaOn ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                luaOn ? (Convert.ToInt32(consent ?? 5) == 0 ? "UAC включён, но запрос согласия для администраторов отключён" : "UAC включён") : "UAC отключён (EnableLUA = 0)")
            .WithEvidence("EnableLUA", lua).WithEvidence("ConsentPromptBehaviorAdmin", consent);
    }
}
