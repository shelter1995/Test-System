using System.Text.Json;

namespace TestSystem.Desktop.Uninstall;

public sealed record ValidatedDataDeletion(string DataDir, string MarkerPath);

public static class DataDeletionGuard
{
    public static void DeleteDataDirectory(string requestedDataDir, Guid installId, string installRoot)
    {
        var validated = ValidateForDeletion(requestedDataDir, installId, installRoot);
        DeleteValidatedDataDirectory(validated);
    }

    public static ValidatedDataDeletion ValidateForDeletion(string requestedDataDir, Guid installId, string installRoot)
    {
        var dataRoot = NormalizeAbsolutePath(requestedDataDir);
        var normalizedInstallRoot = NormalizeAbsolutePath(installRoot);
        EnsureNotProtectedRoot(dataRoot, normalizedInstallRoot);
        EnsureInstallMarkerMatches(dataRoot, installId);
        return new ValidatedDataDeletion(dataRoot, Path.Combine(dataRoot, "config", "install.json"));
    }

    public static void DeleteValidatedDataDirectory(ValidatedDataDeletion deletion)
    {
        DeleteDirectoryContents(deletion.DataDir);
        Directory.Delete(deletion.DataDir);
    }

    private static string NormalizeAbsolutePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
        {
            throw new InvalidOperationException("数据目录必须是 absolute 绝对路径。");
        }

        return TrimTrailingSeparators(Path.GetFullPath(path));
    }

    private static void EnsureNotProtectedRoot(string dataRoot, string installRoot)
    {
        var root = TrimTrailingSeparators(Path.GetPathRoot(dataRoot) ?? string.Empty);
        if (string.Equals(dataRoot, root, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("拒绝删除受保护目录。");
        }

        var protectedRoots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            Environment.GetFolderPath(Environment.SpecialFolder.Windows),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            installRoot,
        }
        .Where(path => !string.IsNullOrWhiteSpace(path))
        .Select(path => TrimTrailingSeparators(Path.GetFullPath(path)))
        .Distinct(StringComparer.OrdinalIgnoreCase);

        foreach (var protectedRoot in protectedRoots)
        {
            if (string.Equals(dataRoot, protectedRoot, StringComparison.OrdinalIgnoreCase)
                || (string.Equals(protectedRoot, installRoot, StringComparison.OrdinalIgnoreCase)
                    && IsInside(dataRoot, protectedRoot)))
            {
                throw new InvalidOperationException("拒绝删除受保护目录。");
            }
        }
    }

    private static void EnsureInstallMarkerMatches(string dataRoot, Guid installId)
    {
        var marker = Path.Combine(dataRoot, "config", "install.json");
        if (!File.Exists(marker))
        {
            throw new InvalidOperationException("找不到数据目录安装标记，已停止删除。");
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(File.ReadAllText(marker, System.Text.Encoding.UTF8));
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException("数据目录安装标记无效，已停止删除。", ex);
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidOperationException("数据目录安装标记无效，已停止删除。");
            }

            if (!root.TryGetProperty("dataDir", out var dataDirElement)
                || dataDirElement.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(dataDirElement.GetString()))
            {
                throw new InvalidOperationException("数据目录安装标记缺少数据目录，已停止删除。");
            }

            var markerDataDir = NormalizeAbsolutePath(dataDirElement.GetString()!);
            if (!string.Equals(markerDataDir, dataRoot, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("数据目录安装标记与当前数据目录不匹配，已停止删除。");
            }

            if (!root.TryGetProperty("installId", out var installIdElement)
                || installIdElement.ValueKind != JsonValueKind.String
                || !Guid.TryParse(installIdElement.GetString(), out var markerInstallId)
                || markerInstallId != installId)
            {
                throw new InvalidOperationException("数据目录安装标识不匹配，已停止删除。");
            }
        }
    }

    private static void DeleteDirectoryContents(string directory)
    {
        foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
        {
            var attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) == FileAttributes.ReparsePoint)
            {
                DeleteReparsePoint(entry, attributes);
                continue;
            }

            if ((attributes & FileAttributes.Directory) == FileAttributes.Directory)
            {
                DeleteDirectoryContents(entry);
                Directory.Delete(entry);
            }
            else
            {
                File.SetAttributes(entry, attributes & ~FileAttributes.ReadOnly);
                File.Delete(entry);
            }
        }
    }

    private static void DeleteReparsePoint(string path, FileAttributes attributes)
    {
        if ((attributes & FileAttributes.Directory) == FileAttributes.Directory)
        {
            Directory.Delete(path);
        }
        else
        {
            File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
            File.Delete(path);
        }
    }

    private static bool IsInside(string candidate, string parent)
    {
        var relative = Path.GetRelativePath(parent, candidate);
        return relative != "."
            && !relative.StartsWith("..", StringComparison.Ordinal)
            && !Path.IsPathFullyQualified(relative);
    }

    private static string TrimTrailingSeparators(string path)
    {
        var root = Path.GetPathRoot(path);
        var trimmed = path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return string.IsNullOrEmpty(trimmed) && root is not null ? root : trimmed;
    }
}
