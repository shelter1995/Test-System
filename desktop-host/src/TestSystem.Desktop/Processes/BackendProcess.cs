using System.Diagnostics;
using System.Text;

namespace TestSystem.Desktop.Processes;

public sealed class BackendProcess : IBackendProcess
{
    private static readonly Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
    private readonly BackendProcessStartInfo _startInfo;
    private readonly WindowsJobObject _jobObject;
    private readonly object _logLock = new();
    private Process? _process;

    public BackendProcess(BackendProcessStartInfo startInfo, WindowsJobObject jobObject)
    {
        _startInfo = startInfo;
        _jobObject = jobObject;
    }

    public string ServiceName => _startInfo.ServiceName;
    public int? ProcessId => _process?.Id;
    public bool HasExited => _process?.HasExited ?? false;
    public int? ExitCode => _process is { HasExited: true } process ? process.ExitCode : null;
    public string LogPath => _startInfo.LogPath;

    public static ProcessStartInfo CreateProcessStartInfo(BackendProcessStartInfo startInfo)
    {
        var processStartInfo = new ProcessStartInfo
        {
            FileName = startInfo.FileName,
            Arguments = startInfo.Arguments,
            WorkingDirectory = startInfo.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };

        processStartInfo.Environment.Clear();
        CopyWindowsEnvironment(processStartInfo.Environment);
        foreach (var pair in startInfo.Environment)
        {
            processStartInfo.Environment[pair.Key] = pair.Value;
        }

        return processStartInfo;
    }

    private static void CopyWindowsEnvironment(IDictionary<string, string?> target)
    {
        foreach (var name in RequiredWindowsEnvironmentNames)
        {
            var value = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(value))
            {
                target[name] = value;
            }
        }
    }

    private static readonly string[] RequiredWindowsEnvironmentNames =
    [
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "NUMBER_OF_PROCESSORS",
        "OS",
    ];

    public Task StartAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!);
        var process = new Process
        {
            StartInfo = CreateProcessStartInfo(_startInfo),
            EnableRaisingEvents = true,
        };

        if (!process.Start())
        {
            throw new InvalidOperationException($"{ServiceName} 后端进程启动失败。");
        }

        try
        {
            _jobObject.Assign(process);
        }
        catch
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }

            process.Dispose();
            throw;
        }

        _process = process;
        _ = Task.Run(() => DrainAsync(process.StandardOutput, "stdout"), CancellationToken.None);
        _ = Task.Run(() => DrainAsync(process.StandardError, "stderr"), CancellationToken.None);
        return Task.CompletedTask;
    }

    public async Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        if (_process is null)
        {
            return true;
        }

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(timeout);
        try
        {
            await _process.WaitForExitAsync(timeoutCts.Token).ConfigureAwait(false);
            return true;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return false;
        }
    }

    public void KillProcessTree()
    {
        try
        {
            if (_process is { HasExited: false } process)
            {
                process.Kill(entireProcessTree: true);
            }
        }
        catch (InvalidOperationException)
        {
        }
    }

    public void Dispose()
    {
        _process?.Dispose();
    }

    private async Task DrainAsync(StreamReader reader, string streamName)
    {
        try
        {
            while (!reader.EndOfStream)
            {
                var line = await reader.ReadLineAsync().ConfigureAwait(false);
                if (line is not null)
                {
                    WriteLog($"[{streamName}] {line}");
                }
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (IOException ex)
        {
            WriteLog($"[{streamName}] 日志读取失败：{ex.Message}");
        }
    }

    private void WriteLog(string line)
    {
        lock (_logLock)
        {
            File.AppendAllText(LogPath, line + Environment.NewLine, Utf8NoBom);
        }
    }
}
