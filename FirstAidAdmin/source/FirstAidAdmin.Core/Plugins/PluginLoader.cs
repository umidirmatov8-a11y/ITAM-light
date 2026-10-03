using System.Reflection;
using System.Runtime.Loader;
using FirstAidAdmin.Core.Abstractions;

namespace FirstAidAdmin.Core.Plugins;

public sealed record PluginLoadReport(string Path, IReadOnlyList<string> ModuleIds, string? Error);

/// <summary>
/// Loads additional diagnostic modules from Plugins\*.dll. Disabled by default (Settings → Diagnostics → LoadPlugins).
/// A plugin type must implement <see cref="IDiagnosticModule"/> and have a public parameterless constructor.
/// Only load plugins from trusted sources: they run with the same rights as the application.
/// </summary>
public sealed class PluginLoader
{
    public List<PluginLoadReport> Reports { get; } = new();

    public IReadOnlyList<IDiagnosticModule> LoadFrom(string folder)
    {
        var modules = new List<IDiagnosticModule>();
        if (!Directory.Exists(folder)) return modules;
        foreach (var dll in Directory.EnumerateFiles(folder, "*.dll"))
            modules.AddRange(LoadAssembly(dll));
        return modules;
    }

    public IReadOnlyList<IDiagnosticModule> LoadAssembly(string path)
    {
        var found = new List<IDiagnosticModule>();
        try
        {
            var context = new AssemblyLoadContext("plugin:" + Path.GetFileNameWithoutExtension(path), isCollectible: false);
            context.Resolving += (ctx, name) =>
            {
                // Share the contract assembly with the host so interface types match.
                if (name.Name == typeof(IDiagnosticModule).Assembly.GetName().Name) return typeof(IDiagnosticModule).Assembly;
                var candidate = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path)!, name.Name + ".dll");
                return File.Exists(candidate) ? ctx.LoadFromAssemblyPath(candidate) : null;
            };
            var asm = context.LoadFromAssemblyPath(System.IO.Path.GetFullPath(path));
            found.AddRange(CreateModules(asm));
            Reports.Add(new PluginLoadReport(path, found.Select(m => m.Id).ToList(), null));
        }
        catch (Exception ex)
        {
            Reports.Add(new PluginLoadReport(path, Array.Empty<string>(), ex.Message));
        }
        return found;
    }

    public static IEnumerable<IDiagnosticModule> CreateModules(Assembly asm)
    {
        Type[] types;
        try { types = asm.GetTypes(); }
        catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t is not null).ToArray()!; }

        foreach (var t in types)
        {
            if (t.IsAbstract || t.IsInterface || !typeof(IDiagnosticModule).IsAssignableFrom(t)) continue;
            if (t.GetCustomAttribute<DiagnosticPluginAttribute>() is null) continue;
            if (t.GetConstructor(Type.EmptyTypes) is null) continue;
            if (Activator.CreateInstance(t) is IDiagnosticModule m) yield return m;
        }
    }
}

/// <summary>Marks a module type as a plugin entry point (explicit opt-in, avoids accidental activation).</summary>
[AttributeUsage(AttributeTargets.Class, Inherited = false)]
public sealed class DiagnosticPluginAttribute : Attribute { }
