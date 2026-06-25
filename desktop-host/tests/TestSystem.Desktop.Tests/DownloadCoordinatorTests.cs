using TestSystem.Desktop.Web;

namespace TestSystem.Desktop.Tests;

public sealed class DownloadCoordinatorTests : IDisposable
{
    private readonly string _root;

    public DownloadCoordinatorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-download-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_root);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Theory]
    [InlineData("bad<>:\"/\\|?*.pdf", "bad.pdf")]
    [InlineData(" name. ", "name")]
    [InlineData("CON", "download")]
    [InlineData("NUL.txt", "download.txt")]
    [InlineData("COM1", "download")]
    [InlineData("   ", "download")]
    [InlineData("...", "download")]
    public void SanitizeSuggestedFileName_removes_dangerous_names(string input, string expected)
    {
        Assert.Equal(expected, DownloadCoordinator.SanitizeSuggestedFileName(input));
    }

    [Fact]
    public async Task Canceling_save_dialog_cancels_download_operation()
    {
        var dialog = new FakeSaveDialog(null);
        var coordinator = new DownloadCoordinator(dialog);

        var result = await coordinator.ResolveAsync(new DownloadRequest("report.pdf"));

        Assert.True(result.Cancel);
        Assert.Null(result.ResultFilePath);
    }

    [Fact]
    public async Task Accepting_save_dialog_sets_result_path_without_reading_content()
    {
        var accepted = Path.Combine(_root, "accepted.pdf");
        var dialog = new FakeSaveDialog(accepted);
        var coordinator = new DownloadCoordinator(dialog);

        var result = await coordinator.ResolveAsync(new DownloadRequest("bad<>name.pdf"));

        Assert.False(result.Cancel);
        Assert.Equal(accepted, result.ResultFilePath);
        Assert.Equal("badname.pdf", dialog.SuggestedName);
        Assert.Equal(0, dialog.ContentReadCount);
    }

    private sealed class FakeSaveDialog(string? acceptedPath) : IFileSaveDialog
    {
        public string? SuggestedName { get; private set; }
        public int ContentReadCount { get; private set; }

        public Task<string?> ShowSaveDialogAsync(string suggestedFileName, CancellationToken cancellationToken = default)
        {
            SuggestedName = suggestedFileName;
            return Task.FromResult(acceptedPath);
        }
    }
}
