using System.Text.Json;
using System.Text.RegularExpressions;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Infrastructure.Commands;
using FirstAidAdmin.Infrastructure.Windows;
using FirstAidAdmin.Remediation;

namespace FirstAidAdmin.Helper;

/// <summary>
/// FirstAidAdmin.Helper.exe — elevated helper started by the main app via UAC ("runas").
/// It executes ONE allow-listed operation (see RemediationCatalog/OperationExecutor), writes the result
/// to a JSON file and exits. It accepts no scripts or arbitrary commands.
/// </summary>
internal static class Program
{
    private static readonly Regex ResultFileName = new(@"^faa-[0-9a-f]{32}\.json$", RegexOptions.IgnoreCase);

    public static async Task<int> Main(string[] args)
    {
        var (op, output, param) = HelperProtocol.Parse(args);
        if (op is null || output is null || !ResultFileName.IsMatch(Path.GetFileName(output)) || !Directory.Exists(Path.GetDirectoryName(output)))
            return 2;

        OperationResult result;
        try
        {
            var runner = new ProcessCommandRunner();
            var executor = new OperationExecutor(runner, new PowerShellRunner(runner), new ShellLauncher());
            if (!executor.IsKnownOperation(op))
                result = OperationResult.Fail($"Операция '{op}' не разрешена");
            else if (!AdminDetector.IsElevated())
                result = OperationResult.Fail("Helper запущен без прав администратора");
            else
                result = await executor.ExecuteAsync(op, param, CancellationToken.None);
        }
        catch (Exception ex)
        {
            result = OperationResult.Fail(ex.Message);
        }

        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(result, JsonDefaults.Compact));
        return result.Success ? 0 : 1;
    }
}
