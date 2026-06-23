using System.Net;
using System.Net.Http;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Startup;

namespace TestSystem.Desktop.Tests;

public sealed class StartupCoordinatorTests : IDisposable
{
    private readonly string _root;

    public StartupCoordinatorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-startup-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_root);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Fact]
    public async Task StartAsync_runs_startup_steps_in_exact_order_and_returns_ready()
    {
        var layout = CreateValidLayout();
        var events = new List<string>();
        var supervisor = new FakeBackendSupervisor(events);
        var probe = new FakeHealthProbe(events, _ => HealthProbeResult.Success());
        var phases = new List<StartupPhase>();
        var coordinator = new StartupCoordinator(
            layout,
            supervisor,
            probe,
            totalTimeout: TimeSpan.FromSeconds(5),
            pollDelay: TimeSpan.Zero,
            stepRecorder: events.Add);

        var result = await coordinator.StartAsync(new InlineProgress<StartupPhase>(phases.Add));

        Assert.True(result.Ready);
        Assert.Null(result.Error);
        Assert.Equal(
            new[]
            {
                "validate-layout",
                "guard-ports",
                "start-rag",
                "probe:http://127.0.0.1:8003/health",
                "start-tutor",
                "probe:http://127.0.0.1:8002/api/status",
            },
            events);
        Assert.Equal(
            new[]
            {
                StartupPhase.ValidatingLayout,
                StartupPhase.GuardingPorts,
                StartupPhase.StartingRag,
                StartupPhase.WaitingForRag,
                StartupPhase.StartingTutor,
                StartupPhase.WaitingForTutor,
                StartupPhase.Ready,
            },
            phases);
    }

    [Fact]
    public async Task StartAsync_retries_transient_health_errors_until_success()
    {
        var layout = CreateValidLayout();
        var attempts = 0;
        var coordinator = new StartupCoordinator(
            layout,
            new FakeBackendSupervisor([]),
            new FakeHealthProbe([], _ =>
            {
                attempts++;
                return attempts == 1
                    ? HealthProbeResult.TransientFailure("connection refused")
                    : HealthProbeResult.Success();
            }),
            totalTimeout: TimeSpan.FromSeconds(5),
            pollDelay: TimeSpan.Zero);

        var result = await coordinator.StartAsync();

        Assert.True(result.Ready);
        Assert.True(attempts >= 2);
    }

    [Theory]
    [InlineData(HttpStatusCode.InternalServerError, "HTTP 500")]
    [InlineData(HttpStatusCode.NotFound, "HTTP 404")]
    public async Task StartAsync_stops_supervisor_and_reports_error_for_non_success_health(HttpStatusCode statusCode, string expectedDetail)
    {
        var layout = CreateValidLayout();
        var supervisor = new FakeBackendSupervisor([]);
        var coordinator = new StartupCoordinator(
            layout,
            supervisor,
            new FakeHealthProbe([], _ => HealthProbeResult.Unhealthy((int)statusCode, expectedDetail)),
            totalTimeout: TimeSpan.FromSeconds(5),
            pollDelay: TimeSpan.Zero);

        var result = await coordinator.StartAsync();

        Assert.False(result.Ready);
        Assert.Equal(1, supervisor.StopCount);
        Assert.NotNull(result.Error);
        Assert.Contains("启动失败", result.Error!.Summary);
        Assert.Contains(expectedDetail, result.Error.Detail);
        Assert.Equal(layout.LogsRoot, result.Error.LogDirectory);
    }

    [Fact]
    public async Task StartAsync_stops_supervisor_when_child_exits_before_ready()
    {
        var layout = CreateValidLayout();
        var supervisor = new FakeBackendSupervisor([])
        {
            ExitBeforeReadyMessage = "RAG 后端服务在就绪前退出，退出码：17。请查看日志：rag.log",
        };
        var coordinator = new StartupCoordinator(
            layout,
            supervisor,
            new FakeHealthProbe([], _ => HealthProbeResult.Success()),
            totalTimeout: TimeSpan.FromSeconds(5),
            pollDelay: TimeSpan.Zero);

        var result = await coordinator.StartAsync();

        Assert.False(result.Ready);
        Assert.Equal(1, supervisor.StopCount);
        Assert.Contains("退出码：17", result.Error!.Detail);
        Assert.Equal(layout.LogsRoot, result.Error.LogDirectory);
    }

    [Fact]
    public async Task StartAsync_honors_cancellation_and_stops_supervisor_once()
    {
        var layout = CreateValidLayout();
        var supervisor = new FakeBackendSupervisor([]);
        using var cts = new CancellationTokenSource();
        var probe = new FakeHealthProbe([], async _ =>
        {
            await cts.CancelAsync();
            return HealthProbeResult.TransientFailure("still starting");
        });
        var coordinator = new StartupCoordinator(
            layout,
            supervisor,
            probe,
            totalTimeout: TimeSpan.FromSeconds(5),
            pollDelay: TimeSpan.FromMilliseconds(1));

        var result = await coordinator.StartAsync(cancellationToken: cts.Token);

        Assert.False(result.Ready);
        Assert.Equal(1, supervisor.StopCount);
        Assert.Contains("已取消", result.Error!.Summary);
    }

    [Fact]
    public async Task StartAsync_uses_total_timeout_and_reports_timeout_error()
    {
        var layout = CreateValidLayout();
        var supervisor = new FakeBackendSupervisor([]);
        var coordinator = new StartupCoordinator(
            layout,
            supervisor,
            new FakeHealthProbe([], _ => HealthProbeResult.TransientFailure("not ready")),
            totalTimeout: TimeSpan.FromMilliseconds(30),
            pollDelay: TimeSpan.FromMilliseconds(5));

        var result = await coordinator.StartAsync();

        Assert.False(result.Ready);
        Assert.Equal(1, supervisor.StopCount);
        Assert.Contains("超时", result.Error!.Summary);
        Assert.Equal(layout.LogsRoot, result.Error.LogDirectory);
    }

    [Fact]
    public void Default_total_timeout_is_120_seconds()
    {
        Assert.Equal(TimeSpan.FromSeconds(120), StartupCoordinator.DefaultTotalTimeout);
    }

    [Fact]
    public async Task HttpHealthProbe_returns_success_for_http_200()
    {
        using var probe = new HttpHealthProbe(new HttpClient(new StaticHttpHandler(new HttpResponseMessage(HttpStatusCode.OK))));

        var result = await probe.ProbeAsync(new Uri("http://127.0.0.1:8003/health"));

        Assert.True(result.Healthy);
    }

    [Fact]
    public async Task HttpHealthProbe_returns_unhealthy_for_non_success_http_status()
    {
        using var probe = new HttpHealthProbe(new HttpClient(new StaticHttpHandler(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable))));

        var result = await probe.ProbeAsync(new Uri("http://127.0.0.1:8003/health"));

        Assert.False(result.Healthy);
        Assert.False(result.Transient);
        Assert.Equal(503, result.StatusCode);
        Assert.Contains("HTTP 503", result.Detail);
    }

    [Fact]
    public async Task HttpHealthProbe_treats_http_request_errors_as_transient()
    {
        using var probe = new HttpHealthProbe(new HttpClient(new StaticHttpHandler(new HttpRequestException("connection refused"))));

        var result = await probe.ProbeAsync(new Uri("http://127.0.0.1:8003/health"));

        Assert.False(result.Healthy);
        Assert.True(result.Transient);
        Assert.Contains("connection refused", result.Detail);
    }

    private RuntimeLayout CreateValidLayout()
    {
        var installRoot = CreateDirectory("install");
        var dataRoot = CreateDirectory("data");
        Directory.CreateDirectory(Path.Combine(installRoot, "runtime", "python"));
        File.WriteAllText(Path.Combine(installRoot, "runtime", "python", "python.exe"), "stub");
        Directory.CreateDirectory(Path.Combine(installRoot, "rag-anything-api"));
        Directory.CreateDirectory(Path.Combine(installRoot, "ai-tutor-system"));
        return RuntimeLayout.Create(installRoot, dataRoot);
    }

    private string CreateDirectory(params string[] parts)
    {
        var path = Path.Combine(new[] { _root }.Concat(parts).ToArray());
        Directory.CreateDirectory(path);
        return path;
    }

    private sealed class FakeBackendSupervisor(List<string> events) : IBackendSupervisor
    {
        public int StopCount { get; private set; }
        public string? ExitBeforeReadyMessage { get; set; }

        public void EnsurePortsAvailable()
        {
            events.Add("guard-ports");
        }

        public Task StartRagAsync(CancellationToken cancellationToken = default)
        {
            events.Add("start-rag");
            return Task.CompletedTask;
        }

        public Task StartTutorAsync(CancellationToken cancellationToken = default)
        {
            events.Add("start-tutor");
            return Task.CompletedTask;
        }

        public void ThrowIfAnyExitedBeforeReady()
        {
            if (ExitBeforeReadyMessage is not null)
            {
                throw new InvalidOperationException(ExitBeforeReadyMessage);
            }
        }

        public Task StopAsync(CancellationToken cancellationToken = default)
        {
            StopCount++;
            return Task.CompletedTask;
        }
    }

    private sealed class FakeHealthProbe : IHealthProbe
    {
        private readonly List<string> _events;
        private readonly Func<Uri, Task<HealthProbeResult>> _resultFactory;

        public FakeHealthProbe(List<string> events, Func<Uri, HealthProbeResult> resultFactory)
            : this(events, uri => Task.FromResult(resultFactory(uri)))
        {
        }

        public FakeHealthProbe(List<string> events, Func<Uri, Task<HealthProbeResult>> resultFactory)
        {
            _events = events;
            _resultFactory = resultFactory;
        }

        public Task<HealthProbeResult> ProbeAsync(Uri uri, CancellationToken cancellationToken = default)
        {
            _events.Add("probe:" + uri);
            return _resultFactory(uri);
        }
    }

    private sealed class StaticHttpHandler : HttpMessageHandler
    {
        private readonly HttpResponseMessage? _response;
        private readonly Exception? _exception;

        public StaticHttpHandler(HttpResponseMessage response)
        {
            _response = response;
        }

        public StaticHttpHandler(Exception exception)
        {
            _exception = exception;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (_exception is not null)
            {
                throw _exception;
            }

            return Task.FromResult(_response!);
        }
    }

    private sealed class InlineProgress<T>(Action<T> handler) : IProgress<T>
    {
        public void Report(T value)
        {
            handler(value);
        }
    }
}
