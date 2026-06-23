using System.IO.Pipes;
using System.Security.Principal;

namespace TestSystem.Desktop.SingleInstance;

public sealed record SingleInstanceNames(string MutexName, string PipeName);

public sealed class SingleInstanceCoordinator : IDisposable
{
    private readonly Mutex _mutex;
    private readonly SynchronizationContext? _synchronizationContext;
    private readonly CancellationTokenSource _serverCancellation = new();
    private Task? _serverTask;
    private bool _disposed;

    private SingleInstanceCoordinator(SingleInstanceNames names, Mutex mutex, bool isPrimary)
    {
        Names = names;
        _mutex = mutex;
        IsPrimary = isPrimary;
        _synchronizationContext = SynchronizationContext.Current;
    }

    public event EventHandler? Activated;

    public SingleInstanceNames Names { get; }
    public bool IsPrimary { get; }

    public static SingleInstanceNames BuildNames(Guid productId)
    {
        var sid = WindowsIdentity.GetCurrent().User?.Value ?? "unknown-user";
        var suffix = $"{sid}-{productId:D}";
        return new SingleInstanceNames(
            MutexName: $@"Local\Test-System-{suffix}",
            PipeName: $"Test-System-{suffix}");
    }

    public static SingleInstanceCoordinator Create(Guid productId)
    {
        var names = BuildNames(productId);
        var mutex = new Mutex(initiallyOwned: true, names.MutexName, out var createdNew);
        return new SingleInstanceCoordinator(names, mutex, createdNew);
    }

    public Task StartActivationServerAsync()
    {
        if (!IsPrimary)
        {
            throw new InvalidOperationException("只有主实例可以启动激活监听。");
        }

        if (_serverTask is not null)
        {
            return Task.CompletedTask;
        }

        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        _serverTask = Task.Run(() => RunServerAsync(ready, _serverCancellation.Token), CancellationToken.None);
        return ready.Task;
    }

    public async Task<int> SignalExistingInstanceAsync(CancellationToken cancellationToken = default)
    {
        if (IsPrimary)
        {
            return 0;
        }

        using var client = new NamedPipeClientStream(
            ".",
            Names.PipeName,
            PipeDirection.Out,
            PipeOptions.Asynchronous);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(2));
        await client.ConnectAsync(timeout.Token).ConfigureAwait(false);
        await using var writer = new StreamWriter(client) { AutoFlush = true };
        await writer.WriteLineAsync("activate").ConfigureAwait(false);
        return 0;
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _serverCancellation.Cancel();
        try
        {
            _serverTask?.Wait(TimeSpan.FromMilliseconds(500));
        }
        catch (AggregateException)
        {
        }

        _serverCancellation.Dispose();
        if (IsPrimary)
        {
            try
            {
                _mutex.ReleaseMutex();
            }
            catch (ApplicationException)
            {
            }
        }

        _mutex.Dispose();
    }

    private async Task RunServerAsync(TaskCompletionSource ready, CancellationToken cancellationToken)
    {
        var reportedReady = false;
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await using var server = new NamedPipeServerStream(
                    Names.PipeName,
                    PipeDirection.In,
                    maxNumberOfServerInstances: 1,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous);
                if (!reportedReady)
                {
                    reportedReady = true;
                    ready.SetResult();
                }

                await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
                using var reader = new StreamReader(server);
                var line = await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false);
                if (string.Equals(line, "activate", StringComparison.Ordinal))
                {
                    RaiseActivated();
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (IOException)
            {
            }
        }
    }

    private void RaiseActivated()
    {
        if (_synchronizationContext is not null)
        {
            _synchronizationContext.Post(_ => Activated?.Invoke(this, EventArgs.Empty), null);
        }
        else
        {
            Activated?.Invoke(this, EventArgs.Empty);
        }
    }
}
