using ITAM.Api.Cli;
using ITAM.Api.Hosting;

namespace ITAM.Api;

public class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args.Length > 0 && CliCommands.IsCommand(args[0]))
            return await CliCommands.RunAsync(args);

        var app = ItamHost.Build(args);
        await app.RunAsync();
        return 0;
    }
}
