namespace TestSystem.Desktop.Startup;

public interface IHealthProbe
{
    Task<HealthProbeResult> ProbeAsync(Uri uri, CancellationToken cancellationToken = default);
}

public sealed record HealthProbeResult(bool Healthy, bool Transient, string Detail, int? StatusCode = null)
{
    public static HealthProbeResult Success()
    {
        return new HealthProbeResult(Healthy: true, Transient: false, Detail: "OK");
    }

    public static HealthProbeResult TransientFailure(string detail)
    {
        return new HealthProbeResult(Healthy: false, Transient: true, Detail: detail);
    }

    public static HealthProbeResult Unhealthy(int statusCode, string detail)
    {
        return new HealthProbeResult(Healthy: false, Transient: false, Detail: detail, StatusCode: statusCode);
    }
}
