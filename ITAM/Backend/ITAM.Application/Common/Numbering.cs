using ITAM.Domain.Numbering;

namespace ITAM.Application.Common;

public interface INumberingService
{
    Task<string> NextAsync(Func<NumberingSettings, string> format, string scope, string? prefix = null, string? regionCode = null, CancellationToken ct = default);
}

public sealed class NumberingService : INumberingService
{
    private readonly ISettingsService _settings;
    private readonly INumberGenerator _gen;
    private readonly IClock _clock;

    public NumberingService(ISettingsService settings, INumberGenerator gen, IClock clock)
    {
        _settings = settings; _gen = gen; _clock = clock;
    }

    public async Task<string> NextAsync(Func<NumberingSettings, string> format, string scope, string? prefix = null, string? regionCode = null, CancellationToken ct = default)
    {
        var cfg = await _settings.GetAsync<NumberingSettings>(ct);
        var pattern = format(cfg);
        var now = _clock.UtcNow;
        var key = NumberFormatter.SequenceKey(scope, pattern, prefix, now, regionCode);
        var seq = await _gen.NextAsync(key, ct);
        return NumberFormatter.Format(pattern, seq, prefix, now, regionCode);
    }
}
