namespace TestSystem.Desktop.Startup;

public sealed class HttpHealthProbe : IHealthProbe, IDisposable
{
    public static readonly TimeSpan DefaultRequestTimeout = TimeSpan.FromSeconds(2);
    private readonly HttpClient _httpClient;
    private readonly bool _ownsClient;
    private readonly TimeSpan _requestTimeout;

    public HttpHealthProbe(HttpClient? httpClient = null, TimeSpan? requestTimeout = null)
    {
        _httpClient = httpClient ?? new HttpClient(new SocketsHttpHandler
        {
            UseProxy = false,
            Proxy = null,
        });
        _ownsClient = httpClient is null;
        _requestTimeout = requestTimeout ?? DefaultRequestTimeout;
    }

    public async Task<HealthProbeResult> ProbeAsync(Uri uri, CancellationToken cancellationToken = default)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(_requestTimeout);
        try
        {
            using var response = await _httpClient.GetAsync(uri, timeout.Token).ConfigureAwait(false);
            if (response.IsSuccessStatusCode)
            {
                return HealthProbeResult.Success();
            }

            return HealthProbeResult.Unhealthy((int)response.StatusCode, $"HTTP {(int)response.StatusCode}");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return HealthProbeResult.TransientFailure("健康检查请求超时");
        }
        catch (HttpRequestException ex)
        {
            return HealthProbeResult.TransientFailure(ex.Message);
        }
    }

    public void Dispose()
    {
        if (_ownsClient)
        {
            _httpClient.Dispose();
        }
    }
}
