namespace ITAM.Application.Common;

/// <summary>Timeline entry built from historical events (business date + recording date).</summary>
public sealed record TimelineItem(
    DateTime Date, DateTime? RecordedAt, string Type, string Title, string? Description,
    string? Link, string? User, bool IsBackdated = false, bool IsCancelled = false, string? Color = null);
