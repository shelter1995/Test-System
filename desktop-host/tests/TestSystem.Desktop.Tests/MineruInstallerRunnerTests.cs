using System.Diagnostics;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Mineru;

namespace TestSystem.Desktop.Tests;

public sealed class MineruInstallerRunnerTests : IDisposable
{
    private readonly string _root;

    public MineruInstallerRunnerTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-mineru-runner-tests", Guid.NewGuid().ToString("N"));
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
    public void Install_mineru_argument_selects_installer_mode()
    {
        Assert.Equal(ApplicationStartupMode.MineruInstaller, Program.SelectStartupMode(["--install-mineru"]));
        Assert.Equal(ApplicationStartupMode.MainApp, Program.SelectStartupMode([]));
    }

    [Fact]
    public async Task Runner_starts_bundled_python_manager_hidden_with_expected_arguments()
    {
        var layout = CreateLayout();
        var launcher = new FakeLauncher();
        var runner = new MineruInstallerRunner(layout, launcher, mainAppMutexOwned: () => false);

        await runner.StartAsync(MineruModelSource.ModelScope);

        var startInfo = launcher.StartInfo!;
        Assert.Equal(layout.PythonExe, startInfo.FileName);
        Assert.Empty(startInfo.Arguments);
        Assert.Contains(Path.Combine("packaging", "mineru_manager.py"), startInfo.ArgumentList[0]);
        Assert.Equal("install", startInfo.ArgumentList[1]);
        Assert.Equal("--package-root", startInfo.ArgumentList[2]);
        Assert.Equal(layout.InstallRoot, startInfo.ArgumentList[3]);
        Assert.Equal("--data-root", startInfo.ArgumentList[4]);
        Assert.Equal(layout.DataRoot, startInfo.ArgumentList[5]);
        Assert.Equal("--source", startInfo.ArgumentList[6]);
        Assert.Equal("modelscope", startInfo.ArgumentList[7]);
        Assert.Equal("--status-json", startInfo.ArgumentList[8]);
        Assert.EndsWith(Path.Combine("runtime", "mineru-status.json"), startInfo.ArgumentList[9]);
        Assert.False(startInfo.UseShellExecute);
        Assert.True(startInfo.CreateNoWindow);
        Assert.True(startInfo.RedirectStandardOutput);
        Assert.True(startInfo.RedirectStandardError);
    }

    [Fact]
    public async Task Runner_parses_json_progress_from_manager_stdout()
    {
        var layout = CreateLayout();
        var process = new FakeManagedProcess
        {
            OutputLines =
            [
                """{"stage":"dependencies","percent":10,"message":"正在安装增强解析依赖（MinerU / FFmpeg / Whisper）"}""",
                """{"stage":"complete","percent":100,"message":"增强解析组件安装完成（MinerU / FFmpeg / Whisper）"}""",
            ],
        };
        var runner = new MineruInstallerRunner(layout, new FakeLauncher(process), mainAppMutexOwned: () => false);
        var progress = new List<MineruInstallProgress>();

        var result = await runner.StartAsync(MineruModelSource.ModelScope, new InlineProgress<MineruInstallProgress>(progress.Add));

        Assert.True(result.Success);
        Assert.Equal("dependencies", progress[0].Stage);
        Assert.Equal(10, progress[0].Percent);
        Assert.Equal("增强解析组件安装完成（MinerU / FFmpeg / Whisper）", progress[^1].Message);
    }

    [Fact]
    public async Task Cancel_terminates_only_manager_process_tree()
    {
        var layout = CreateLayout();
        var process = new FakeManagedProcess { WaitForExitResult = false };
        var runner = new MineruInstallerRunner(layout, new FakeLauncher(process), mainAppMutexOwned: () => false);
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        var result = await runner.StartAsync(MineruModelSource.ModelScope, cancellationToken: cts.Token);

        Assert.False(result.Success);
        Assert.True(process.KillTreeCalled);
        Assert.Contains("取消", result.Message);
    }

    [Fact]
    public async Task Failure_result_includes_log_path()
    {
        var layout = CreateLayout();
        var process = new FakeManagedProcess
        {
            ExitCode = 2,
            ErrorLines = ["pip failed"],
        };
        var runner = new MineruInstallerRunner(layout, new FakeLauncher(process), mainAppMutexOwned: () => false);

        var result = await runner.StartAsync(MineruModelSource.ModelScope);

        Assert.False(result.Success);
        Assert.Equal(Path.Combine(layout.LogsRoot, "mineru-installer.log"), result.LogPath);
        Assert.Contains("pip failed", File.ReadAllText(result.LogPath));
    }

    [Fact]
    public async Task Runner_serializes_stdout_and_stderr_into_same_log()
    {
        var layout = CreateLayout();
        var process = new FakeManagedProcess
        {
            OutputLines = ["""{"stage":"dependencies","percent":10,"message":"正在安装"}"""],
            ErrorLines = ["warning line"],
        };
        var runner = new MineruInstallerRunner(layout, new FakeLauncher(process), mainAppMutexOwned: () => false);

        var result = await runner.StartAsync(MineruModelSource.ModelScope);

        var log = File.ReadAllText(result.LogPath);
        Assert.Contains("dependencies", log);
        Assert.Contains("warning line", log);
    }

    [Fact]
    public async Task Runner_refuses_to_modify_packages_while_main_app_mutex_is_owned()
    {
        var layout = CreateLayout();
        var runner = new MineruInstallerRunner(layout, new FakeLauncher(), mainAppMutexOwned: () => true);

        var result = await runner.StartAsync(MineruModelSource.ModelScope);

        Assert.False(result.Success);
        Assert.Contains("请先关闭智学工作台", result.Message);
    }

    private RuntimeLayout CreateLayout()
    {
        var installRoot = Path.Combine(_root, "install") + Path.DirectorySeparatorChar;
        var dataRoot = Path.Combine(_root, "data");
        Directory.CreateDirectory(Path.Combine(installRoot, "runtime", "python"));
        File.WriteAllText(Path.Combine(installRoot, "runtime", "python", "python.exe"), "stub");
        Directory.CreateDirectory(dataRoot);
        return RuntimeLayout.Create(installRoot, dataRoot);
    }

    private sealed class FakeLauncher : IMineruProcessLauncher
    {
        private readonly FakeManagedProcess _process;

        public FakeLauncher()
            : this(new FakeManagedProcess())
        {
        }

        public FakeLauncher(FakeManagedProcess process)
        {
            _process = process;
        }

        public ProcessStartInfo? StartInfo { get; private set; }

        public IManagedMineruProcess Start(ProcessStartInfo startInfo)
        {
            StartInfo = startInfo;
            return _process;
        }
    }

    private sealed class InlineProgress<T>(Action<T> handler) : IProgress<T>
    {
        public void Report(T value)
        {
            handler(value);
        }
    }

    private sealed class FakeManagedProcess : IManagedMineruProcess
    {
        public IReadOnlyList<string> OutputLines { get; init; } = [];
        public IReadOnlyList<string> ErrorLines { get; init; } = [];
        public bool WaitForExitResult { get; init; } = true;
        public int ExitCode { get; init; }
        public bool KillTreeCalled { get; private set; }

        public IAsyncEnumerable<string> ReadStdoutLinesAsync(CancellationToken cancellationToken = default)
        {
            return Enumerate(OutputLines, cancellationToken);
        }

        public IAsyncEnumerable<string> ReadStderrLinesAsync(CancellationToken cancellationToken = default)
        {
            return Enumerate(ErrorLines, cancellationToken);
        }

        public Task<bool> WaitForExitAsync(CancellationToken cancellationToken = default)
        {
            return Task.FromResult(WaitForExitResult);
        }

        public void KillProcessTree()
        {
            KillTreeCalled = true;
        }

        public void Dispose()
        {
        }

        private static async IAsyncEnumerable<string> Enumerate(
            IReadOnlyList<string> lines,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            foreach (var line in lines)
            {
                cancellationToken.ThrowIfCancellationRequested();
                yield return line;
                await Task.Yield();
            }
        }
    }
}
