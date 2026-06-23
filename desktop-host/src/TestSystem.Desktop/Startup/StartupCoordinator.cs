using TestSystem.Desktop.Configuration;

namespace TestSystem.Desktop.Startup;

public interface IBackendSupervisor
{
    void EnsurePortsAvailable();
    Task StartRagAsync(CancellationToken cancellationToken = default);
    Task StartTutorAsync(CancellationToken cancellationToken = default);
    void ThrowIfAnyExitedBeforeReady();
    Task StopAsync(CancellationToken cancellationToken = default);
}

public enum StartupPhase
{
    ValidatingLayout,
    GuardingPorts,
    StartingRag,
    WaitingForRag,
    StartingTutor,
    WaitingForTutor,
    Ready,
}

public sealed record StartupError(string Summary, string Detail, string LogDirectory);

public sealed record StartupResult(bool Ready, StartupError? Error)
{
    public static StartupResult Success()
    {
        return new StartupResult(Ready: true, Error: null);
    }

    public static StartupResult Failure(StartupError error)
    {
        return new StartupResult(Ready: false, Error: error);
    }
}

public sealed class StartupCoordinator
{
    public static readonly TimeSpan DefaultTotalTimeout = TimeSpan.FromSeconds(120);
    private static readonly TimeSpan DefaultPollDelay = TimeSpan.FromSeconds(1);

    private readonly RuntimeLayout _layout;
    private readonly IBackendSupervisor _supervisor;
    private readonly IHealthProbe _healthProbe;
    private readonly TimeSpan _totalTimeout;
    private readonly TimeSpan _pollDelay;
    private readonly Action<string>? _stepRecorder;

    public StartupCoordinator(
        RuntimeLayout layout,
        IBackendSupervisor supervisor,
        IHealthProbe healthProbe,
        TimeSpan? totalTimeout = null,
        TimeSpan? pollDelay = null,
        Action<string>? stepRecorder = null)
    {
        _layout = layout;
        _supervisor = supervisor;
        _healthProbe = healthProbe;
        _totalTimeout = totalTimeout ?? DefaultTotalTimeout;
        _pollDelay = pollDelay ?? DefaultPollDelay;
        _stepRecorder = stepRecorder;
    }

    public async Task<StartupResult> StartAsync(
        IProgress<StartupPhase>? progress = null,
        CancellationToken cancellationToken = default)
    {
        using var timeout = new CancellationTokenSource(_totalTimeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        var stopped = false;

        async Task<StartupResult> FailAsync(string summary, string detail)
        {
            if (!stopped)
            {
                stopped = true;
                await _supervisor.StopAsync(CancellationToken.None).ConfigureAwait(false);
            }

            return StartupResult.Failure(new StartupError(summary, detail, _layout.LogsRoot));
        }

        try
        {
            Report(progress, StartupPhase.ValidatingLayout, "validate-layout");
            ValidateLayout();

            Report(progress, StartupPhase.GuardingPorts);
            _supervisor.EnsurePortsAvailable();

            Report(progress, StartupPhase.StartingRag);
            await _supervisor.StartRagAsync(linked.Token).ConfigureAwait(false);

            Report(progress, StartupPhase.WaitingForRag);
            await WaitForHealthyAsync(new Uri("http://127.0.0.1:8003/health"), linked.Token).ConfigureAwait(false);

            Report(progress, StartupPhase.StartingTutor);
            await _supervisor.StartTutorAsync(linked.Token).ConfigureAwait(false);

            Report(progress, StartupPhase.WaitingForTutor);
            await WaitForHealthyAsync(new Uri("http://127.0.0.1:8002/api/status"), linked.Token).ConfigureAwait(false);

            Report(progress, StartupPhase.Ready);
            return StartupResult.Success();
        }
        catch (OperationCanceledException)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                return await FailAsync("启动已取消", "用户取消了 Test-System 启动。").ConfigureAwait(false);
            }

            return await FailAsync("启动超时", $"后端服务未能在 {_totalTimeout.TotalSeconds:0} 秒内启动完成。").ConfigureAwait(false);
        }
        catch (StartupFailureException ex)
        {
            return await FailAsync("启动失败", ex.Message).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            return await FailAsync("启动失败", ex.Message).ConfigureAwait(false);
        }
    }

    private void ValidateLayout()
    {
        if (!File.Exists(_layout.PythonExe))
        {
            throw new InvalidOperationException($"找不到内置 Python：{_layout.PythonExe}");
        }

        if (!Directory.Exists(_layout.RagRoot))
        {
            throw new InvalidOperationException($"找不到知识库服务目录：{_layout.RagRoot}");
        }

        if (!Directory.Exists(_layout.TutorRoot))
        {
            throw new InvalidOperationException($"找不到 AI 陪练服务目录：{_layout.TutorRoot}");
        }

        Directory.CreateDirectory(_layout.LogsRoot);
    }

    private async Task WaitForHealthyAsync(Uri uri, CancellationToken cancellationToken)
    {
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            _supervisor.ThrowIfAnyExitedBeforeReady();

            var result = await _healthProbe.ProbeAsync(uri, cancellationToken).ConfigureAwait(false);
            if (result.Healthy)
            {
                return;
            }

            if (!result.Transient)
            {
                throw new StartupFailureException(result.Detail);
            }

            _supervisor.ThrowIfAnyExitedBeforeReady();
            if (_pollDelay > TimeSpan.Zero)
            {
                await Task.Delay(_pollDelay, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await Task.Yield();
            }
        }
    }

    private void Report(IProgress<StartupPhase>? progress, StartupPhase phase, string? step = null)
    {
        progress?.Report(phase);
        if (step is not null)
        {
            _stepRecorder?.Invoke(step);
        }
    }

    private sealed class StartupFailureException(string message) : Exception(message);
}
