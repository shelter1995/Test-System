namespace TestSystem.Desktop.Web;

public sealed record DownloadRequest(string SuggestedFileName);

public sealed record DownloadResolution(bool Cancel, string? ResultFilePath)
{
    public static DownloadResolution Canceled()
    {
        return new DownloadResolution(Cancel: true, ResultFilePath: null);
    }

    public static DownloadResolution Accepted(string path)
    {
        return new DownloadResolution(Cancel: false, ResultFilePath: path);
    }
}

public sealed class DownloadCoordinator
{
    private static readonly HashSet<string> ReservedDeviceNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    };

    private readonly IFileSaveDialog _saveDialog;

    public DownloadCoordinator(IFileSaveDialog saveDialog)
    {
        _saveDialog = saveDialog;
    }

    public async Task<DownloadResolution> ResolveAsync(DownloadRequest request, CancellationToken cancellationToken = default)
    {
        var safeName = SanitizeSuggestedFileName(request.SuggestedFileName);
        var result = await _saveDialog.ShowSaveDialogAsync(safeName, cancellationToken).ConfigureAwait(true);
        return string.IsNullOrWhiteSpace(result)
            ? DownloadResolution.Canceled()
            : DownloadResolution.Accepted(result);
    }

    public static string SanitizeSuggestedFileName(string? suggestedFileName)
    {
        var text = string.IsNullOrWhiteSpace(suggestedFileName) ? "download" : suggestedFileName.Trim();
        foreach (var invalid in Path.GetInvalidFileNameChars().Concat(['<', '>', ':', '"', '/', '\\', '|', '?', '*']))
        {
            text = text.Replace(invalid.ToString(), "");
        }

        text = text.Trim().TrimEnd('.', ' ');
        if (string.IsNullOrWhiteSpace(text))
        {
            return "download";
        }

        var extension = Path.GetExtension(text);
        var stem = extension.Length == 0 ? text : text[..^extension.Length];
        if (string.IsNullOrWhiteSpace(stem) || ReservedDeviceNames.Contains(stem))
        {
            return "download" + extension;
        }

        return text;
    }
}
