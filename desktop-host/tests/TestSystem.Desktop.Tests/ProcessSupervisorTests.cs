using System.Net;
using System.Net.Sockets;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Processes;

namespace TestSystem.Desktop.Tests;

public sealed class ProcessSupervisorTests : IDisposable
{
    private readonly string _root;

    public ProcessSupervisorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-process-tests", Guid.NewGuid().ToString("N"));
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
    public async Task Supervisor_builds_python_commands_with_bundled_executable_and_service_working_directories()
    {
        var layout = RuntimeLayout.Create(CreateDirectory("install"), CreateDirectory("data"));
        var env = new Dictionary<string, string> { ["PATH"] = "only-explicit-path" };
        var started = new List<BackendProcessStartInfo>();
        var supervisor = new BackendProcessSupervisor(
            layout,
            env,
            "shutdown-token",
            processFactory: info =>
            {
                started.Add(info);
                return new FakeBackendProcess(info);
            },
            portGuard: new FakePortGuard(),
            httpClient: new HttpClient(new RecordingHandler()));

        await supervisor.StartRagAsync();
        await supervisor.StartTutorAsync();

        Assert.Collection(
            started,
            rag =>
            {
                Assert.Equal("RAG", rag.ServiceName);
                Assert.Equal(layout.PythonExe, rag.FileName);
                Assert.Equal("start.py", rag.Arguments);
                Assert.Equal(layout.RagRoot, rag.WorkingDirectory);
                Assert.Equal(env, rag.Environment);
            },
            tutor =>
            {
                Assert.Equal("Tutor", tutor.ServiceName);
                Assert.Equal(layout.PythonExe, tutor.FileName);
                Assert.Equal("tutor_backend.py", tutor.Arguments);
                Assert.Equal(layout.TutorRoot, tutor.WorkingDirectory);
            });
    }

    [Fact]
    public void BackendProcess_start_info_hides_console_redirects_output_and_replaces_environment()
    {
        var info = new BackendProcessStartInfo(
            "RAG",
            @"C:\App\runtime\python\python.exe",
            "start.py",
            @"C:\App\rag-anything-api",
            @"C:\Data\logs\rag.log",
            new Dictionary<string, string>
            {
                ["PATH"] = @"C:\App\runtime\python",
                ["TEST_SYSTEM_DATA_DIR"] = @"C:\Data",
            },
            new Uri("http://127.0.0.1:8003/__desktop/shutdown"),
            8003);

        var startInfo = BackendProcess.CreateProcessStartInfo(info);

        Assert.False(startInfo.UseShellExecute);
        Assert.True(startInfo.CreateNoWindow);
        Assert.True(startInfo.RedirectStandardOutput);
        Assert.True(startInfo.RedirectStandardError);
        Assert.Equal(info.FileName, startInfo.FileName);
        Assert.Equal(info.Arguments, startInfo.Arguments);
        Assert.Equal(info.WorkingDirectory, startInfo.WorkingDirectory);
        Assert.Equal(2, startInfo.Environment.Count);
        Assert.Equal(@"C:\Data", startInfo.Environment["TEST_SYSTEM_DATA_DIR"]);
    }

    [Fact]
    public async Task Supervisor_reports_child_exit_before_readiness_with_exit_code_and_log_path()
    {
        var layout = RuntimeLayout.Create(CreateDirectory("install"), CreateDirectory("data"));
        var process = new FakeBackendProcess(
            new BackendProcessStartInfo("RAG", "python", "start.py", layout.RagRoot, Path.Combine(layout.LogsRoot, "rag.log"), new Dictionary<string, string>(), new Uri("http://127.0.0.1:8003/__desktop/shutdown"), 8003))
        {
            HasExitedValue = true,
            ExitCodeValue = 17,
        };
        var supervisor = new BackendProcessSupervisor(
            layout,
            new Dictionary<string, string>(),
            "shutdown-token",
            processFactory: _ => process,
            portGuard: new FakePortGuard(),
            httpClient: new HttpClient(new RecordingHandler()));
        await supervisor.StartRagAsync();

        var error = Assert.Throws<InvalidOperationException>(() => supervisor.ThrowIfAnyExitedBeforeReady());

        Assert.Contains("RAG", error.Message);
        Assert.Contains("17", error.Message);
        Assert.Contains("rag.log", error.Message);
    }

    [Fact]
    public async Task Stop_posts_shutdown_token_to_each_owned_process_then_waits()
    {
        var layout = RuntimeLayout.Create(CreateDirectory("install"), CreateDirectory("data"));
        var handler = new RecordingHandler();
        var processes = new List<FakeBackendProcess>();
        var supervisor = new BackendProcessSupervisor(
            layout,
            new Dictionary<string, string>(),
            "shutdown-token",
            processFactory: info =>
            {
                var process = new FakeBackendProcess(info);
                processes.Add(process);
                return process;
            },
            portGuard: new FakePortGuard(),
            httpClient: new HttpClient(handler),
            shutdownTimeout: TimeSpan.FromMilliseconds(50));
        await supervisor.StartRagAsync();
        await supervisor.StartTutorAsync();

        await supervisor.StopAsync();

        Assert.Equal(new[] { "http://127.0.0.1:8003/__desktop/shutdown", "http://127.0.0.1:8002/__desktop/shutdown" }, handler.RequestUris);
        Assert.All(handler.ShutdownTokens, token => Assert.Equal("shutdown-token", token));
        Assert.All(processes, process => Assert.True(process.WaitCalled));
    }

    [Fact]
    public async Task Stop_kills_remaining_owned_processes_after_timeout()
    {
        var layout = RuntimeLayout.Create(CreateDirectory("install"), CreateDirectory("data"));
        var processes = new List<FakeBackendProcess>();
        var supervisor = new BackendProcessSupervisor(
            layout,
            new Dictionary<string, string>(),
            "shutdown-token",
            processFactory: info =>
            {
                var process = new FakeBackendProcess(info) { WaitResult = false };
                processes.Add(process);
                return process;
            },
            portGuard: new FakePortGuard(),
            httpClient: new HttpClient(new RecordingHandler()),
            shutdownTimeout: TimeSpan.FromMilliseconds(20));
        await supervisor.StartRagAsync();
        await supervisor.StartTutorAsync();

        await supervisor.StopAsync();

        Assert.All(processes, process => Assert.True(process.KillCalled));
    }

    [Fact]
    public void Port_guard_rejects_unowned_listener_without_killing_it()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        var guard = new PortOwnershipGuard();

        var error = Assert.Throws<InvalidOperationException>(() => guard.EnsureAvailable(("测试服务", port)));

        Assert.Contains(port.ToString(), error.Message);
        Assert.True(listener.Server.IsBound);
    }

    private string CreateDirectory(params string[] parts)
    {
        var path = Path.Combine(new[] { _root }.Concat(parts).ToArray());
        Directory.CreateDirectory(path);
        return path;
    }

    private sealed class FakePortGuard : IPortOwnershipGuard
    {
        public void EnsureAvailable(params (string ServiceName, int Port)[] ports)
        {
        }
    }

    private sealed class FakeBackendProcess(BackendProcessStartInfo startInfo) : IBackendProcess
    {
        public BackendProcessStartInfo StartInfo { get; } = startInfo;
        public bool HasExitedValue { get; set; }
        public int? ExitCodeValue { get; set; }
        public bool WaitResult { get; set; } = true;
        public bool WaitCalled { get; private set; }
        public bool KillCalled { get; private set; }

        public string ServiceName => StartInfo.ServiceName;
        public int? ProcessId => 1234;
        public bool HasExited => HasExitedValue;
        public int? ExitCode => ExitCodeValue;
        public string LogPath => StartInfo.LogPath;

        public Task StartAsync(CancellationToken cancellationToken = default)
        {
            return Task.CompletedTask;
        }

        public Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken = default)
        {
            WaitCalled = true;
            return Task.FromResult(WaitResult);
        }

        public void KillProcessTree()
        {
            KillCalled = true;
        }

        public void Dispose()
        {
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public List<string> RequestUris { get; } = [];
        public List<string?> ShutdownTokens { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            RequestUris.Add(request.RequestUri!.ToString());
            ShutdownTokens.Add(request.Headers.TryGetValues("X-Test-System-Shutdown-Token", out var values) ? values.Single() : null);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        }
    }
}
