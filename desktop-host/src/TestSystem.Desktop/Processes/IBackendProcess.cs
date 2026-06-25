namespace TestSystem.Desktop.Processes;

public interface IBackendProcess : IDisposable
{
    string ServiceName { get; }
    int? ProcessId { get; }
    bool HasExited { get; }
    int? ExitCode { get; }
    string LogPath { get; }

    Task StartAsync(CancellationToken cancellationToken = default);
    Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken = default);
    void KillProcessTree();
}

public sealed record BackendProcessStartInfo(
    string ServiceName,
    string FileName,
    string Arguments,
    string WorkingDirectory,
    string LogPath,
    IReadOnlyDictionary<string, string> Environment,
    Uri ShutdownUri,
    int Port);
