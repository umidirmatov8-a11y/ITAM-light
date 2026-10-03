using ITAM.Application.Auth;
using ITAM.Application.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Finance;
using ITAM.Domain.Numbering;

namespace ITAM.UnitTests;

public class NumberFormatterTests
{
    [Theory]
    [InlineData("{PREFIX}-{SEQ:6}", 123, "LPT", "LPT-000123")]
    [InlineData("{PREFIX}{SEQ}", 7, "MON", "MON7")]
    [InlineData("ISS-{YYYY}-{SEQ:5}", 42, null, "ISS-2026-00042")]
    [InlineData("{REGION}-{PREFIX}-{YY}{MM}-{SEQ:4}", 9, "PC", "TAS-PC-2610-0009")]
    public void Formats_patterns(string pattern, long seq, string? prefix, string expected)
        => Assert.Equal(expected, NumberFormatter.Format(pattern, seq, prefix, new DateTime(2026, 10, 3), "TAS"));

    [Fact]
    public void Sequence_never_truncated_when_longer_than_padding()
        => Assert.Equal("LPT-1234567", NumberFormatter.Format("{PREFIX}-{SEQ:6}", 1234567, "LPT"));

    [Fact]
    public void Yearly_and_regional_patterns_get_separate_counters()
    {
        var d = new DateTime(2026, 1, 1);
        Assert.Equal("asset:LPT", NumberFormatter.SequenceKey("asset", "{PREFIX}-{SEQ:6}", "LPT", d, "TAS"));
        Assert.Equal("issue:2026", NumberFormatter.SequenceKey("issue", "ISS-{YYYY}-{SEQ}", null, d, null));
        Assert.Equal("asset:PC:SAM", NumberFormatter.SequenceKey("asset", "{REGION}-{PREFIX}-{SEQ}", "PC", d, "SAM"));
    }

    [Fact]
    public void Pattern_must_contain_sequence()
    {
        Assert.True(NumberFormatter.IsValidPattern("{PREFIX}-{SEQ:6}"));
        Assert.False(NumberFormatter.IsValidPattern("{PREFIX}-{YYYY}"));
    }
}

public class DepreciationTests
{
    [Fact]
    public void Straight_line_after_one_year()
    {
        var r = DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, 1200m, 0m, new DateOnly(2025, 1, 15), 36, new DateOnly(2026, 1, 15))!;
        Assert.Equal(12, r.MonthsElapsed);
        Assert.Equal(33.33m, r.MonthlyAmount);
        Assert.Equal(1200m - r.Accumulated, r.BookValue);
        Assert.False(r.IsFullyDepreciated);
    }

    [Fact]
    public void Straight_line_never_goes_below_salvage()
    {
        var r = DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, 1000m, 100m, new DateOnly(2020, 1, 1), 12, new DateOnly(2026, 1, 1))!;
        Assert.True(r.IsFullyDepreciated);
        Assert.Equal(100m, r.BookValue);
    }

    [Fact]
    public void Declining_balance_is_front_loaded_and_ends_at_salvage()
    {
        var sl = DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, 1000m, 0m, new DateOnly(2025, 1, 1), 24, new DateOnly(2025, 7, 1))!;
        var ddb = DepreciationCalculator.Calculate(DepreciationMethod.DecliningBalance, 1000m, 0m, new DateOnly(2025, 1, 1), 24, new DateOnly(2025, 7, 1))!;
        Assert.True(ddb.Accumulated > sl.Accumulated);
        var end = DepreciationCalculator.Calculate(DepreciationMethod.DecliningBalance, 1000m, 50m, new DateOnly(2020, 1, 1), 24, new DateOnly(2026, 1, 1))!;
        Assert.Equal(50m, end.BookValue);
    }

    [Fact]
    public void Missing_data_returns_null()
    {
        Assert.Null(DepreciationCalculator.Calculate(DepreciationMethod.None, 1000m, 0, new DateOnly(2025, 1, 1), 12, new DateOnly(2026, 1, 1)));
        Assert.Null(DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, null, 0, new DateOnly(2025, 1, 1), 12, new DateOnly(2026, 1, 1)));
        Assert.Null(DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, 1000m, 0, null, 12, new DateOnly(2026, 1, 1)));
    }

    [Fact]
    public void Purchase_in_future_means_zero_elapsed()
    {
        var r = DepreciationCalculator.Calculate(DepreciationMethod.StraightLine, 1000m, 0, new DateOnly(2027, 1, 1), 12, new DateOnly(2026, 1, 1))!;
        Assert.Equal(0, r.MonthsElapsed);
        Assert.Equal(1000m, r.BookValue);
    }
}

public class PasswordPolicyTests
{
    private static readonly SecuritySettings Defaults = new();

    [Theory]
    [InlineData("Admin12345!")]
    [InlineData("Pa55wordLong")]
    public void Accepts_strong_passwords(string p) => Assert.Empty(PasswordPolicy.Validate(p, Defaults));

    [Theory]
    [InlineData("short1A")]
    [InlineData("alllowercase123")]
    [InlineData("ALLUPPERCASE123")]
    [InlineData("NoDigitsHereAtAll")]
    public void Rejects_weak_passwords(string p) => Assert.NotEmpty(PasswordPolicy.Validate(p, Defaults));

    [Fact]
    public void Special_character_requirement()
    {
        var s = new SecuritySettings { RequireSpecial = true };
        Assert.NotEmpty(PasswordPolicy.Validate("Password12345", s));
        Assert.Empty(PasswordPolicy.Validate("Password12345!", s));
    }

    [Fact]
    public void Ensure_throws_validation_exception()
        => Assert.Throws<ITAM.Domain.Common.ValidationFailedException>(() => PasswordPolicy.Ensure("x", Defaults));
}
