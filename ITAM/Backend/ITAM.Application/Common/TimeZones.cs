namespace ITAM.Application.Common;

public static class TimeZones
{
    public static TimeZoneInfo Resolve(string? id)
    {
        if (!string.IsNullOrWhiteSpace(id))
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); }
            catch (Exception ex) when (ex is TimeZoneNotFoundException or InvalidTimeZoneException)
            {
                if (TimeZoneInfo.TryConvertIanaIdToWindowsId(id, out var win))
                    try { return TimeZoneInfo.FindSystemTimeZoneById(win); } catch { /* fall through */ }
            }
        }
        // Asia/Tashkent: UTC+5, no DST.
        return TimeZoneInfo.CreateCustomTimeZone("UTC+05", TimeSpan.FromHours(5), "UTC+05", "UTC+05");
    }

    public static DateTime ToLocal(DateTime utc, TimeZoneInfo tz)
        => TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), tz);
}
