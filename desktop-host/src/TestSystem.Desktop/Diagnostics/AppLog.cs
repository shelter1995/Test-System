using System.Text;

namespace TestSystem.Desktop.Diagnostics;

public sealed class AppLog
{
    private const long MaxBytes = 5L * 1024L * 1024L;
    private const int MaxRotatedFiles = 5;
    private static readonly Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
    private readonly string _logFile;

    public AppLog(string dataRoot)
    {
        _logFile = Path.Combine(dataRoot, "logs", "desktop-host.log");
    }

    public void Write(string message)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_logFile)!);
            RotateIfNeeded();
            File.AppendAllText(
                _logFile,
                $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss.fff zzz} {message}{Environment.NewLine}",
                Utf8NoBom);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
        {
        }
    }

    private void RotateIfNeeded()
    {
        var info = new FileInfo(_logFile);
        if (!info.Exists || info.Length <= MaxBytes)
        {
            return;
        }

        var oldest = RotatedPath(MaxRotatedFiles);
        if (File.Exists(oldest))
        {
            File.Delete(oldest);
        }

        for (var index = MaxRotatedFiles - 1; index >= 1; index--)
        {
            var source = RotatedPath(index);
            if (File.Exists(source))
            {
                File.Move(source, RotatedPath(index + 1));
            }
        }

        File.Move(_logFile, RotatedPath(1));
    }

    private string RotatedPath(int index)
    {
        return Path.Combine(Path.GetDirectoryName(_logFile)!, $"desktop-host.{index}.log");
    }
}
