using System.Text.Json;
using TestSystem.Desktop.Uninstall;

namespace TestSystem.Desktop.Tests;

public sealed class DataDeletionGuardTests : IDisposable
{
    private readonly string _root;
    private readonly string _installRoot;
    private readonly Guid _installId = Guid.NewGuid();

    public DataDeletionGuardTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-data-deletion-guard-tests", Guid.NewGuid().ToString("N"));
        _installRoot = Path.Combine(_root, "install");
        Directory.CreateDirectory(_installRoot);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("relative-data")]
    public void Validate_rejects_empty_or_relative_paths(string requestedPath)
    {
        var error = Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(requestedPath, _installId, _installRoot));

        Assert.Contains("absolute", error.Message);
    }

    [Fact]
    public void Validate_rejects_drive_root()
    {
        var driveRoot = Path.GetPathRoot(Path.GetTempPath())!;

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(driveRoot, _installId, _installRoot));
    }

    [Fact]
    public void Validate_rejects_user_profile_root()
    {
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(profile, _installId, _installRoot));
    }

    [Fact]
    public void Validate_rejects_windows_root()
    {
        var windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(windows, _installId, _installRoot));
    }

    [Fact]
    public void Validate_rejects_program_files_roots()
    {
        foreach (var folder in new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
        }.Where(path => !string.IsNullOrWhiteSpace(path)).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            Assert.Throws<InvalidOperationException>(
                () => DataDeletionGuard.ValidateForDeletion(folder, _installId, _installRoot));
        }
    }

    [Fact]
    public void Validate_rejects_local_app_data_root()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(localAppData, _installId, _installRoot));
    }

    [Fact]
    public void Validate_rejects_install_root()
    {
        WriteMarker(_installRoot, _installRoot, _installId);

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(_installRoot, _installId, _installRoot));
    }

    [Fact]
    public void Validate_allows_only_exact_configured_data_directory_with_matching_install_id_marker()
    {
        var dataRoot = Path.Combine(_root, "data");
        WriteMarker(dataRoot, dataRoot, _installId);

        var result = DataDeletionGuard.ValidateForDeletion(dataRoot, _installId, _installRoot);

        Assert.Equal(Path.GetFullPath(dataRoot), result.DataDir);
        Assert.Equal(Path.Combine(dataRoot, "config", "install.json"), result.MarkerPath);
    }

    [Fact]
    public void Validate_rejects_when_marker_records_different_data_directory()
    {
        var dataRoot = Path.Combine(_root, "data");
        var otherDataRoot = Path.Combine(_root, "other-data");
        WriteMarker(dataRoot, otherDataRoot, _installId);

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(dataRoot, _installId, _installRoot));
    }

    [Fact]
    public void Validate_rejects_when_marker_records_different_install_id()
    {
        var dataRoot = Path.Combine(_root, "data");
        WriteMarker(dataRoot, dataRoot, Guid.NewGuid());

        Assert.Throws<InvalidOperationException>(
            () => DataDeletionGuard.ValidateForDeletion(dataRoot, _installId, _installRoot));
    }

    [Fact]
    public void DeleteValidatedDataDirectory_deletes_contents_and_root()
    {
        var dataRoot = Path.Combine(_root, "data");
        WriteMarker(dataRoot, dataRoot, _installId);
        File.WriteAllText(Path.Combine(dataRoot, "notes.txt"), "delete me");
        var validated = DataDeletionGuard.ValidateForDeletion(dataRoot, _installId, _installRoot);

        DataDeletionGuard.DeleteValidatedDataDirectory(validated);

        Assert.False(Directory.Exists(dataRoot));
    }

    [Fact]
    public void Delete_data_argument_selects_delete_mode()
    {
        Assert.Equal(
            ApplicationStartupMode.DataDeletion,
            Program.SelectStartupMode(["--delete-data", Path.Combine(_root, "data"), "--install-id", _installId.ToString("D")]));
    }

    private static void WriteMarker(string dataRoot, string recordedDataRoot, Guid installId)
    {
        var configRoot = Path.Combine(dataRoot, "config");
        Directory.CreateDirectory(configRoot);
        File.WriteAllText(
            Path.Combine(configRoot, "install.json"),
            JsonSerializer.Serialize(new { dataDir = recordedDataRoot, installId }),
            System.Text.Encoding.UTF8);
    }
}
