using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.App.Converters;

/// <summary>Maps DiagnosticStatus / Severity / RiskLevel to the theme brushes.</summary>
public sealed class StatusBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var key = value switch
        {
            DiagnosticStatus.Ok => "OkBrush",
            DiagnosticStatus.Warning => "WarnBrush",
            DiagnosticStatus.Error => "ErrBrush",
            DiagnosticStatus.Critical => "CritBrush",
            DiagnosticStatus.Skipped => "SkipBrush",
            DiagnosticStatus.Info => "InfoBrush",
            Severity.Critical => "CritBrush",
            Severity.High => "ErrBrush",
            Severity.Medium => "WarnBrush",
            Severity.Low => "InfoBrush",
            RiskLevel.High => "ErrBrush",
            RiskLevel.Medium => "WarnBrush",
            RiskLevel.Low => "OkBrush",
            _ => "MutedBrush"
        };
        return System.Windows.Application.Current?.TryFindResource(key) as Brush ?? Brushes.Gray;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => Binding.DoNothing;
}

public sealed class BoolToVisibilityConverter : IValueConverter
{
    public bool Invert { get; set; }
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var b = value switch
        {
            bool x => x,
            int i => i > 0,
            string s => !string.IsNullOrWhiteSpace(s),
            null => false,
            _ => true
        };
        if (Invert) b = !b;
        return b ? Visibility.Visible : Visibility.Collapsed;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => Binding.DoNothing;
}
