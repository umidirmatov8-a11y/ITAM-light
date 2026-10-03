using System.Diagnostics;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.Core.Engine;

/// <summary>Runs the local target: modules execute in this process.</summary>
public sealed class LocalDiagnosticTarget : IDiagnosticTarget
{
    public string DisplayName => Environment.MachineName;
    public bool IsLocal => true;
    public Task<DiagnosticResult> RunModuleAsync(IDiagnosticModule module, DiagnosticContext context, CancellationToken cancellationToken)
        => module.RunAsync(context, cancellationToken);
}

/// <summary>Runs a set of modules safely: per-module timeout, cancellation, exception isolation, progress.</summary>
public sealed class DiagnosticRunner
{
    private readonly IReadOnlyDictionary<string, IDiagnosticModule> _modules;
    private readonly IDiagnosticTarget _target;

    public DiagnosticRunner(IEnumerable<IDiagnosticModule> modules, IDiagnosticTarget? target = null)
    {
        var dict = new Dictionary<string, IDiagnosticModule>(StringComparer.OrdinalIgnoreCase);
        foreach (var m in modules) dict[m.Id] = m; // plugins with the same id replace built-ins
        _modules = dict;
        _target = target ?? new LocalDiagnosticTarget();
    }

    public IReadOnlyCollection<IDiagnosticModule> Modules => _modules.Values.ToList();
    public IDiagnosticModule? Find(string id) => _modules.TryGetValue(id, out var m) ? m : null;

    /// <summary>Upper bound for one module. Long-running modules (SFC/DISM) get much more.</summary>
    public static TimeSpan ModuleTimeout(IDiagnosticModule module)
        => module is IDiagnosticModuleInfo { IsLongRunning: true } ? TimeSpan.FromMinutes(45) : TimeSpan.FromMinutes(4);

    public async Task<List<DiagnosticResult>> RunAsync(IEnumerable<string> moduleIds, DiagnosticContext context, CancellationToken cancellationToken)
    {
        var ids = moduleIds.Distinct(StringComparer.OrdinalIgnoreCase)
            .Where(id => !context.Settings.Diagnostics.DisabledModules.Contains(id, StringComparer.OrdinalIgnoreCase))
            .ToList();
        var results = new List<DiagnosticResult>();
        for (var i = 0; i < ids.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var id = ids[i];
            if (!_modules.TryGetValue(id, out var module))
            {
                context.Logger.LogWarning("Module {ModuleId} is not registered", id);
                continue;
            }

            context.Progress?.Report(new DiagnosticProgress { ModuleId = id, ModuleName = module.Name, Index = i, Total = ids.Count, Message = $"{module.Name}: выполняется…" });
            var result = await RunOneAsync(module, context, cancellationToken).ConfigureAwait(false);
            results.Add(result);
            context.PreviousResults[id] = result;
            context.Progress?.Report(new DiagnosticProgress { ModuleId = id, ModuleName = module.Name, Index = i + 1, Total = ids.Count, Result = result, Message = $"{module.Name}: {result.Summary}" });
        }
        return results;
    }

    public async Task<DiagnosticResult> RunOneAsync(IDiagnosticModule module, DiagnosticContext context, CancellationToken cancellationToken)
    {
        var sw = Stopwatch.StartNew();
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(ModuleTimeout(module));
        DiagnosticResult result;
        try
        {
            context.Logger.LogInformation("Module {ModuleId} started", module.Id);
            result = await _target.RunModuleAsync(module, context, timeoutCts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            result = DiagnosticResult.Create(module.Id, module.Name, CategoryOf(module), DiagnosticStatus.Warning,
                "Превышено время выполнения модуля");
        }
        catch (Exception ex)
        {
            context.Logger.LogError(ex, "Module {ModuleId} failed", module.Id);
            result = DiagnosticResult.Create(module.Id, module.Name, CategoryOf(module), DiagnosticStatus.Warning,
                    $"Модуль завершился с исключением: {ex.GetType().Name}")
                .WithDetails(ex.Message);
        }
        sw.Stop();
        if (string.IsNullOrEmpty(result.Id)) result.Id = module.Id;
        if (string.IsNullOrEmpty(result.Name)) result.Name = module.Name;
        result.Duration = sw.Elapsed;
        SeverityEngine.Normalize(result);
        context.Logger.LogInformation("Module {ModuleId} finished: {Status} in {DurationMs} ms", module.Id, result.Status, sw.ElapsedMilliseconds);
        return result;
    }

    private static DiagnosticCategory CategoryOf(IDiagnosticModule m) => m is IDiagnosticModuleInfo info ? info.Category : DiagnosticCategory.System;
}
