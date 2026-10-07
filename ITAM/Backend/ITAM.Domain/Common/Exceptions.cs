namespace ITAM.Domain.Common;

/// <summary>Business rule violation. Converted by the API into HTTP 400/409/422 with a stable error code.</summary>
public class BusinessException : Exception
{
    public string Code { get; }
    public object? Details { get; }
    public virtual int StatusCode => 400;

    public BusinessException(string code, string message, object? details = null) : base(message)
    {
        Code = code;
        Details = details;
    }
}

public class NotFoundException : BusinessException
{
    public override int StatusCode => 404;
    public NotFoundException(string entity, object? id = null)
        : base("NOT_FOUND", id is null ? $"{entity} не найден(а)" : $"{entity} не найден(а): {id}") { }
}

public class ConflictException : BusinessException
{
    public override int StatusCode => 409;
    public ConflictException(string code, string message, object? details = null) : base(code, message, details) { }
}

public class ForbiddenException : BusinessException
{
    public override int StatusCode => 403;
    public ForbiddenException(string message = "Недостаточно прав для выполнения операции")
        : base("FORBIDDEN", message) { }
}

public class ValidationFailedException : BusinessException
{
    public override int StatusCode => 422;
    public ValidationFailedException(string message, IDictionary<string, string[]>? errors = null)
        : base("VALIDATION_FAILED", message, errors) { }
}

public static class ErrorCodes
{
    public const string AssetAlreadyAssigned = "ASSET_ALREADY_ASSIGNED";
    public const string AssetNotIssuable = "ASSET_NOT_ISSUABLE";
    public const string AssetNotAssigned = "ASSET_NOT_ASSIGNED";
    public const string AssetInRepair = "ASSET_IN_REPAIR";
    public const string AssetConcurrentModification = "ASSET_CONCURRENT_MODIFICATION";
    public const string ConcurrentModification = "CONCURRENT_MODIFICATION";
    public const string TemporalConflict = "TEMPORAL_CONFLICT";
    public const string BackdateNotAllowed = "BACKDATE_NOT_ALLOWED";
    public const string FutureDate = "OPERATION_DATE_IN_FUTURE";
    public const string InvalidStatusTransition = "INVALID_STATUS_TRANSITION";
    public const string ReactivationForbidden = "REACTIVATION_FORBIDDEN";
    public const string HasDependencies = "HAS_DEPENDENCIES";
    public const string Duplicate = "DUPLICATE";
    public const string LicenseNoSeats = "LICENSE_NO_SEATS";
    public const string LicenseExpired = "LICENSE_EXPIRED";
    public const string OutOfRegionScope = "OUT_OF_REGION_SCOPE";
    public const string InvalidCredentials = "INVALID_CREDENTIALS";
    public const string AccountLocked = "ACCOUNT_LOCKED";
    public const string PasswordPolicy = "PASSWORD_POLICY";
    public const string SetupCompleted = "SETUP_ALREADY_COMPLETED";
    public const string OpenItems = "EMPLOYEE_HAS_OPEN_ITEMS";
}
