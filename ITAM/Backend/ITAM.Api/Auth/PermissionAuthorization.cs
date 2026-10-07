using ITAM.Domain.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Options;

namespace ITAM.Api.Auth;

/// <summary>[HasPermission("assets.assign")] → policy "perm:assets.assign".</summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
public sealed class HasPermissionAttribute : AuthorizeAttribute
{
    public const string Prefix = "perm:";
    public HasPermissionAttribute(string permission) : base(Prefix + permission) { }
}

public sealed class PermissionRequirement(string permission) : IAuthorizationRequirement
{
    public string Permission { get; } = permission;
}

public sealed class PermissionHandler : AuthorizationHandler<PermissionRequirement>
{
    protected override Task HandleRequirementAsync(AuthorizationHandlerContext context, PermissionRequirement requirement)
    {
        var perms = context.User.FindAll(ItamClaims.Permission).Select(c => c.Value).ToHashSet();
        if (perms.Contains(requirement.Permission) || perms.Contains(Permissions.SystemAdmin)) context.Succeed(requirement);
        return Task.CompletedTask;
    }
}

public sealed class PermissionPolicyProvider : DefaultAuthorizationPolicyProvider
{
    public PermissionPolicyProvider(IOptions<AuthorizationOptions> options) : base(options) { }

    public override async Task<AuthorizationPolicy?> GetPolicyAsync(string policyName)
    {
        if (policyName.StartsWith(HasPermissionAttribute.Prefix, StringComparison.Ordinal))
            return new AuthorizationPolicyBuilder(SessionAuthenticationHandler.Scheme)
                .RequireAuthenticatedUser()
                .AddRequirements(new PermissionRequirement(policyName[HasPermissionAttribute.Prefix.Length..]))
                .Build();
        return await base.GetPolicyAsync(policyName);
    }
}
