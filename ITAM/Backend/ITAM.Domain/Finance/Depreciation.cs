using ITAM.Domain.Enums;

namespace ITAM.Domain.Finance;

public sealed record DepreciationInfo(
    DepreciationMethod Method, int UsefulLifeMonths, int MonthsElapsed, decimal Cost, decimal Salvage,
    decimal MonthlyAmount, decimal Accumulated, decimal BookValue, DateOnly FullyDepreciatedOn, bool IsFullyDepreciated);

/// <summary>Book value calculation (straight-line or double-declining balance, monthly granularity).</summary>
public static class DepreciationCalculator
{
    public static DepreciationInfo? Calculate(DepreciationMethod method, decimal? cost, decimal? salvage, DateOnly? purchaseDate, int? usefulLifeMonths, DateOnly asOf)
    {
        if (method == DepreciationMethod.None || cost is null or <= 0 || purchaseDate is null || usefulLifeMonths is null or <= 0) return null;
        var life = usefulLifeMonths.Value;
        var salv = Math.Max(0, salvage ?? 0);
        var basis = Math.Max(0, cost.Value - salv);
        var elapsed = Math.Clamp((asOf.Year - purchaseDate.Value.Year) * 12 + asOf.Month - purchaseDate.Value.Month - (asOf.Day < purchaseDate.Value.Day ? 1 : 0), 0, life);
        decimal accumulated, monthly;
        if (method == DepreciationMethod.StraightLine)
        {
            monthly = Math.Round(basis / life, 2);
            accumulated = elapsed >= life ? basis : Math.Min(basis, monthly * elapsed);
        }
        else
        {
            // Double-declining balance with switch-over to straight line in the remaining life.
            var rate = 2m / life;
            var book = cost.Value;
            accumulated = 0;
            monthly = 0;
            for (var m = 0; m < elapsed; m++)
            {
                var remaining = life - m;
                var ddb = book * rate;
                var sl = (book - salv) / remaining;
                monthly = Math.Max(ddb, sl);
                if (book - monthly < salv) monthly = book - salv;
                book -= monthly;
                accumulated += monthly;
            }
            monthly = Math.Round(monthly, 2);
            accumulated = Math.Round(accumulated, 2);
        }
        var bookValue = Math.Round(cost.Value - accumulated, 2);
        return new DepreciationInfo(method, life, elapsed, cost.Value, salv, monthly, Math.Round(accumulated, 2), bookValue,
            purchaseDate.Value.AddMonths(life), elapsed >= life);
    }
}
