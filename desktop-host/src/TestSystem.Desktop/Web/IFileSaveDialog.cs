namespace TestSystem.Desktop.Web;

public interface IFileSaveDialog
{
    Task<string?> ShowSaveDialogAsync(string suggestedFileName, CancellationToken cancellationToken = default);
}
