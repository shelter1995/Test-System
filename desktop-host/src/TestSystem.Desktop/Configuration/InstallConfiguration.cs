using System.Text.Json;

namespace TestSystem.Desktop.Configuration;

public sealed record InstallConfiguration(string InstallRoot, string DataDir, Guid InstallId)
{
    public static InstallConfiguration Load(string installRoot)
    {
        var normalizedInstallRoot = NormalizeAbsolutePath(installRoot, "安装目录必须是绝对路径");
        var configPath = Path.Combine(normalizedInstallRoot, "install-location.json");
        if (!File.Exists(configPath))
        {
            throw new InvalidOperationException("找不到安装配置文件，请重新安装 Test-System。");
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(File.ReadAllText(configPath, System.Text.Encoding.UTF8));
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException("安装配置文件格式无效，请重新安装 Test-System。", ex);
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidOperationException("安装配置文件格式无效，请重新安装 Test-System。");
            }

            if (!root.TryGetProperty("dataDir", out var dataDirElement)
                || dataDirElement.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(dataDirElement.GetString()))
            {
                throw new InvalidOperationException("数据目录缺失或为空，请重新安装 Test-System。");
            }

            var dataDir = dataDirElement.GetString()!;
            if (!Path.IsPathFullyQualified(dataDir))
            {
                throw new InvalidOperationException("数据目录必须是绝对路径，请重新安装 Test-System。");
            }

            if (!root.TryGetProperty("installId", out var installIdElement)
                || installIdElement.ValueKind != JsonValueKind.String
                || !Guid.TryParse(installIdElement.GetString(), out var installId))
            {
                throw new InvalidOperationException("安装标识缺失或无效，请重新安装 Test-System。");
            }

            return new InstallConfiguration(
                normalizedInstallRoot,
                Path.GetFullPath(dataDir),
                installId);
        }
    }

    private static string NormalizeAbsolutePath(string path, string message)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
        {
            throw new InvalidOperationException(message);
        }

        return Path.GetFullPath(path);
    }
}
