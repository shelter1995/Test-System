using System.Diagnostics;
using System.Text;
using System.Text.Json;
using TestSystem.Desktop.Configuration;

namespace TestSystem.Desktop.Mineru;

public enum MineruModelSource
{
    ModelScope,
    HuggingFace,
}

public sealed record MineruInstallProgress(string Stage, int Percent, string Message);

public sealed record MineruInstallResult(bool Success, string Message, string LogPath)
{
    public static MineruInstallResult Ok(string logPath)
    {
        return new MineruInstallResult(true, "增强解析组件安装完成", logPath);
    }

    public static MineruInstallResult Fail(string message, string logPath)
    {
        return new MineruInstallResult(false, message, logPath);
    }
}

public interface IMineruProcessLauncher
{
    IManagedMineruProcess Start(ProcessStartInfo startInfo);
}

public interface IManagedMineruProcess : IDisposable
{
    IAsyncEnumerable<string> ReadStdoutLinesAsync(CancellationToken cancellationToken = default);
    IAsyncEnumerable<string> ReadStderrLinesAsync(CancellationToken cancellationToken = default);
    Task<bool> WaitForExitAsync(CancellationToken cancellationToken = default);
    int ExitCode { get; }
    void KillProcessTree();
}

public sealed class MineruInstallerRunner
{
    private readonly RuntimeLayout _layout;
    private readonly IMineruProcessLauncher _launcher;
    private readonly Func<bool> _mainAppMutexOwned;
    private readonly object _logLock = new();

    public MineruInstallerRunner(
        RuntimeLayout layout,
        IMineruProcessLauncher? launcher = null,
        Func<bool>? mainAppMutexOwned = null)
    {
        _layout = layout;
        _launcher = launcher ?? new MineruProcessLauncher();
        _mainAppMutexOwned = mainAppMutexOwned ?? (() => false);
    }

    public async Task<MineruInstallResult> StartAsync(
        MineruModelSource source,
        IProgress<MineruInstallProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var logPath = Path.Combine(_layout.LogsRoot, "mineru-installer.log");
        Directory.CreateDirectory(_layout.LogsRoot);
        if (_mainAppMutexOwned())
        {
            return MineruInstallResult.Fail("请先关闭智学工作台主程序后再安装增强解析组件。", logPath);
        }

        using var process = _launcher.Start(BuildStartInfo(source, logPath));
        try
        {
            var stdoutTask = ConsumeStdoutAsync(process, progress, logPath, cancellationToken);
            var stderrTask = ConsumeStderrAsync(process, logPath, cancellationToken);
            if (cancellationToken.IsCancellationRequested)
            {
                process.KillProcessTree();
                return MineruInstallResult.Fail("安装已取消。", logPath);
            }

            var exited = await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
            if (!exited || cancellationToken.IsCancellationRequested)
            {
                process.KillProcessTree();
                return MineruInstallResult.Fail("安装已取消。", logPath);
            }

            await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);
            return process.ExitCode == 0
                ? MineruInstallResult.Ok(logPath)
                : MineruInstallResult.Fail($"增强解析组件安装失败，退出码：{process.ExitCode}。日志：{logPath}", logPath);
        }
        catch (OperationCanceledException)
        {
            process.KillProcessTree();
            return MineruInstallResult.Fail("安装已取消。", logPath);
        }
    }

    private ProcessStartInfo BuildStartInfo(MineruModelSource source, string logPath)
    {
        var sourceValue = source == MineruModelSource.HuggingFace ? "huggingface" : "modelscope";
        var manager = Path.Combine(_layout.InstallRoot, "packaging", "mineru_manager.py");
        var statusJson = Path.Combine(_layout.RuntimeRoot, "mineru-status.json");
        var arguments = string.Join(
            " ",
            Quote(manager),
            "install",
            "--package-root",
            Quote(_layout.InstallRoot),
            "--data-root",
            Quote(_layout.DataRoot),
            "--source",
            sourceValue,
            "--status-json",
            Quote(statusJson));

        var startInfo = new ProcessStartInfo
        {
            FileName = _layout.PythonExe,
            Arguments = arguments,
            WorkingDirectory = _layout.InstallRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
        startInfo.Environment["TEST_SYSTEM_DATA_DIR"] = _layout.DataRoot;
        startInfo.Environment["TEST_SYSTEM_LOG_DIR"] = _layout.LogsRoot;
        startInfo.Environment["TEST_SYSTEM_MINERU_LOG"] = logPath;
        return startInfo;
    }

    private async Task ConsumeStdoutAsync(
        IManagedMineruProcess process,
        IProgress<MineruInstallProgress>? progress,
        string logPath,
        CancellationToken cancellationToken)
    {
        await foreach (var line in process.ReadStdoutLinesAsync(cancellationToken).ConfigureAwait(false))
        {
            AppendLog(logPath, line);
            if (TryParseProgress(line, out var item))
            {
                progress?.Report(item);
            }
        }
    }

    private async Task ConsumeStderrAsync(IManagedMineruProcess process, string logPath, CancellationToken cancellationToken)
    {
        await foreach (var line in process.ReadStderrLinesAsync(cancellationToken).ConfigureAwait(false))
        {
            AppendLog(logPath, line);
        }
    }

    private static bool TryParseProgress(string line, out MineruInstallProgress progress)
    {
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            progress = new MineruInstallProgress(
                root.GetProperty("stage").GetString() ?? "",
                root.GetProperty("percent").GetInt32(),
                root.GetProperty("message").GetString() ?? "");
            return true;
        }
        catch (JsonException)
        {
            progress = new MineruInstallProgress("", 0, "");
            return false;
        }
        catch (KeyNotFoundException)
        {
            progress = new MineruInstallProgress("", 0, "");
            return false;
        }
    }

    private void AppendLog(string logPath, string line)
    {
        lock (_logLock)
        {
            File.AppendAllText(logPath, line + Environment.NewLine, Encoding.UTF8);
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"", StringComparison.Ordinal) + "\"";
    }
}

public sealed class MineruProcessLauncher : IMineruProcessLauncher
{
    public IManagedMineruProcess Start(ProcessStartInfo startInfo)
    {
        var process = Process.Start(startInfo) ?? throw new InvalidOperationException("无法启动 MinerU 安装进程。");
        return new ManagedMineruProcess(process);
    }
}

public sealed class ManagedMineruProcess : IManagedMineruProcess
{
    private readonly Process _process;

    public ManagedMineruProcess(Process process)
    {
        _process = process;
    }

    public int ExitCode => _process.HasExited ? _process.ExitCode : -1;

    public async IAsyncEnumerable<string> ReadStdoutLinesAsync(
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        while (true)
        {
            var line = await _process.StandardOutput.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
            {
                yield break;
            }

            yield return line;
        }
    }

    public async IAsyncEnumerable<string> ReadStderrLinesAsync(
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        while (true)
        {
            var line = await _process.StandardError.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
            {
                yield break;
            }

            yield return line;
        }
    }

    public async Task<bool> WaitForExitAsync(CancellationToken cancellationToken = default)
    {
        await _process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        return true;
    }

    public void KillProcessTree()
    {
        if (!_process.HasExited)
        {
            _process.Kill(entireProcessTree: true);
        }
    }

    public void Dispose()
    {
        _process.Dispose();
    }
}
