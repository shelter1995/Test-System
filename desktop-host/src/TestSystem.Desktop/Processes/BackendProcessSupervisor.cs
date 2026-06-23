using TestSystem.Desktop.Configuration;

namespace TestSystem.Desktop.Processes;

public sealed class BackendProcessSupervisor : IDisposable
{
    public const int DefaultTutorPort = 8002;
    public const int DefaultRagPort = 8003;
    public static readonly TimeSpan DefaultShutdownTimeout = TimeSpan.FromSeconds(10);

    private readonly RuntimeLayout _layout;
    private readonly IReadOnlyDictionary<string, string> _environment;
    private readonly string _shutdownToken;
    private readonly Func<BackendProcessStartInfo, IBackendProcess> _processFactory;
    private readonly IPortOwnershipGuard _portGuard;
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly TimeSpan _shutdownTimeout;
    private readonly int _tutorPort;
    private readonly int _ragPort;
    private readonly WindowsJobObject? _jobObject;
    private readonly List<IBackendProcess> _processes = [];
    private readonly Dictionary<IBackendProcess, BackendProcessStartInfo> _startInfos = [];
    private bool _disposed;

    public BackendProcessSupervisor(
        RuntimeLayout layout,
        IReadOnlyDictionary<string, string> environment,
        string shutdownToken,
        Func<BackendProcessStartInfo, IBackendProcess>? processFactory = null,
        IPortOwnershipGuard? portGuard = null,
        HttpClient? httpClient = null,
        TimeSpan? shutdownTimeout = null,
        int tutorPort = DefaultTutorPort,
        int ragPort = DefaultRagPort)
    {
        _layout = layout;
        _environment = environment;
        _shutdownToken = shutdownToken;
        _portGuard = portGuard ?? new PortOwnershipGuard();
        _httpClient = httpClient ?? new HttpClient();
        _ownsHttpClient = httpClient is null;
        _shutdownTimeout = shutdownTimeout ?? DefaultShutdownTimeout;
        _tutorPort = tutorPort;
        _ragPort = ragPort;
        if (processFactory is null)
        {
            _jobObject = new WindowsJobObject();
            _processFactory = info => new BackendProcess(info, _jobObject);
        }
        else
        {
            _processFactory = processFactory;
        }
    }

    public void EnsurePortsAvailable()
    {
        _portGuard.EnsureAvailable(("AI 陪练服务", _tutorPort), ("知识库服务", _ragPort));
    }

    public Task StartRagAsync(CancellationToken cancellationToken = default)
    {
        return StartAsync(CreateRagStartInfo(), cancellationToken);
    }

    public Task StartTutorAsync(CancellationToken cancellationToken = default)
    {
        return StartAsync(CreateTutorStartInfo(), cancellationToken);
    }

    public void ThrowIfAnyExitedBeforeReady()
    {
        foreach (var process in _processes)
        {
            if (process.HasExited)
            {
                throw new InvalidOperationException(
                    $"{process.ServiceName} 后端服务在就绪前退出，退出码：{process.ExitCode?.ToString() ?? "未知"}。请查看日志：{process.LogPath}");
            }
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        var alive = _processes.Where(process => !process.HasExited).ToArray();
        await Task.WhenAll(alive.Select(process => PostShutdownAsync(process, cancellationToken))).ConfigureAwait(false);
        await Task.WhenAll(alive.Select(process => StopOneAsync(process, cancellationToken))).ConfigureAwait(false);
        Dispose();
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        foreach (var process in _processes)
        {
            process.Dispose();
        }

        _jobObject?.Dispose();
        if (_ownsHttpClient)
        {
            _httpClient.Dispose();
        }
    }

    private async Task StartAsync(BackendProcessStartInfo startInfo, CancellationToken cancellationToken)
    {
        var process = _processFactory(startInfo);
        _processes.Add(process);
        _startInfos[process] = startInfo;
        await process.StartAsync(cancellationToken).ConfigureAwait(false);
    }

    private BackendProcessStartInfo CreateRagStartInfo()
    {
        return new BackendProcessStartInfo(
            "RAG",
            _layout.PythonExe,
            "start.py",
            _layout.RagRoot,
            Path.Combine(_layout.LogsRoot, "rag-service.log"),
            _environment,
            new Uri($"http://127.0.0.1:{_ragPort}/__desktop/shutdown"),
            _ragPort);
    }

    private BackendProcessStartInfo CreateTutorStartInfo()
    {
        return new BackendProcessStartInfo(
            "Tutor",
            _layout.PythonExe,
            "tutor_backend.py",
            _layout.TutorRoot,
            Path.Combine(_layout.LogsRoot, "tutor-service.log"),
            _environment,
            new Uri($"http://127.0.0.1:{_tutorPort}/__desktop/shutdown"),
            _tutorPort);
    }

    private async Task PostShutdownAsync(IBackendProcess process, CancellationToken cancellationToken)
    {
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, _startInfos[process].ShutdownUri);
            request.Headers.TryAddWithoutValidation("X-Test-System-Shutdown-Token", _shutdownToken);
            using var _ = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or OperationCanceledException)
        {
        }
    }

    private async Task StopOneAsync(IBackendProcess process, CancellationToken cancellationToken)
    {
        var exited = await process.WaitForExitAsync(_shutdownTimeout, cancellationToken).ConfigureAwait(false);
        if (!exited && !process.HasExited)
        {
            process.KillProcessTree();
        }
    }
}
