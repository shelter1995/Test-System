using System.Text;

namespace TestSystem.Desktop.Configuration;

public sealed record RuntimeLayout(
    string InstallRoot,
    string DataRoot,
    string PythonExe,
    string RagRoot,
    string TutorRoot,
    string LogsRoot,
    string WebViewUserData,
    string OptionalSitePackages,
    string MineruModels,
    string ConfigRoot,
    string RuntimeRoot,
    string ToolsRoot)
{
    public static RuntimeLayout Create(string installRoot, string dataRoot)
    {
        var normalizedInstallRoot = NormalizeAbsolutePath(installRoot, "安装目录必须是绝对路径");
        var normalizedDataRoot = NormalizeAbsolutePath(dataRoot, "数据目录必须是绝对路径");
        var runtimeRoot = Path.Combine(normalizedDataRoot, "runtime");

        return new RuntimeLayout(
            normalizedInstallRoot,
            normalizedDataRoot,
            Path.Combine(normalizedInstallRoot, "runtime", "python", "python.exe"),
            Path.Combine(normalizedInstallRoot, "rag-anything-api"),
            Path.Combine(normalizedInstallRoot, "ai-tutor-system"),
            Path.Combine(normalizedDataRoot, "logs"),
            Path.Combine(runtimeRoot, "webview2-user-data"),
            Path.Combine(runtimeRoot, "optional-site-packages"),
            Path.Combine(normalizedDataRoot, "models", "mineru"),
            Path.Combine(normalizedDataRoot, "config"),
            runtimeRoot,
            Path.Combine(normalizedInstallRoot, "runtime", "tools"));
    }

    public void EnsureWritableDirectories()
    {
        foreach (var path in new[]
        {
            DataRoot,
            LogsRoot,
            WebViewUserData,
            OptionalSitePackages,
            MineruModels,
            ConfigRoot,
            Path.Combine(DataRoot, "rag", "storage"),
            Path.Combine(DataRoot, "rag", "output"),
            Path.Combine(DataRoot, "tutor_data"),
            Path.Combine(DataRoot, "generation_output"),
        })
        {
            Directory.CreateDirectory(path);
            ProbeWritableDirectory(path);
        }

        CopyEnvExampleIfMissing(Path.Combine(RagRoot, ".env.example"), Path.Combine(ConfigRoot, "rag.env"));
        CopyEnvExampleIfMissing(Path.Combine(TutorRoot, ".env.example"), Path.Combine(ConfigRoot, "tutor.env"));
    }

    private static string NormalizeAbsolutePath(string path, string message)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
        {
            throw new InvalidOperationException(message);
        }

        return Path.GetFullPath(path);
    }

    private static void ProbeWritableDirectory(string directory)
    {
        var probe = Path.Combine(directory, $".write-probe-{Guid.NewGuid():N}.tmp");
        var renamed = probe + ".renamed";
        try
        {
            File.WriteAllText(probe, "ok", Encoding.UTF8);
            File.Move(probe, renamed);
            File.Delete(renamed);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException($"目录不可写：{directory}", ex);
        }
        finally
        {
            TryDelete(probe);
            TryDelete(renamed);
        }
    }

    private static void CopyEnvExampleIfMissing(string source, string destination)
    {
        if (!File.Exists(source) || File.Exists(destination))
        {
            return;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        using var input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read);
        using var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        input.CopyTo(output);
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
