namespace TestSystem.Desktop.Web;

public sealed class WindowsFileSaveDialog : IFileSaveDialog
{
    public Task<string?> ShowSaveDialogAsync(string suggestedFileName, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        using var dialog = new SaveFileDialog
        {
            FileName = suggestedFileName,
            InitialDirectory = GetDownloadsDirectory(),
            OverwritePrompt = true,
            AddExtension = true,
            CheckPathExists = true,
            Title = "保存下载文件",
        };

        return Task.FromResult(dialog.ShowDialog() == DialogResult.OK ? dialog.FileName : null);
    }

    private static string GetDownloadsDirectory()
    {
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var downloads = Path.Combine(profile, "Downloads");
        return Directory.Exists(downloads) ? downloads : profile;
    }
}
