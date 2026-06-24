using System.Text.Json;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Diagnostics;

namespace TestSystem.Desktop.Tests;

public sealed class ConfigurationTests : IDisposable
{
    private readonly string _root;

    public ConfigurationTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-desktop-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_root);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Fact]
    public void Load_accepts_absolute_data_dir_and_guid_install_id()
    {
        var installRoot = CreateDirectory("Program Files", "Test-System");
        var dataRoot = CreateDirectory("User Data", "Test-System");
        var installId = Guid.NewGuid();
        WriteInstallLocation(installRoot, new { dataDir = dataRoot, installId });

        var config = InstallConfiguration.Load(installRoot);

        Assert.Equal(Path.GetFullPath(installRoot), config.InstallRoot);
        Assert.Equal(Path.GetFullPath(dataRoot), config.DataDir);
        Assert.Equal(installId, config.InstallId);
    }

    [Theory]
    [InlineData(null, "找不到安装配置文件")]
    [InlineData("{", "安装配置文件格式无效")]
    [InlineData("""{"installId":"2f8f38dc-1043-4509-9c1d-8bcecd601156"}""", "数据目录")]
    [InlineData("""{"dataDir":"","installId":"2f8f38dc-1043-4509-9c1d-8bcecd601156"}""", "数据目录")]
    [InlineData("""{"dataDir":"relative-data","installId":"2f8f38dc-1043-4509-9c1d-8bcecd601156"}""", "数据目录必须是绝对路径")]
    [InlineData("""{"dataDir":"C:\\Test-System\\Data"}""", "安装标识")]
    [InlineData("""{"dataDir":"C:\\Test-System\\Data","installId":"not-a-guid"}""", "安装标识")]
    public void Load_rejects_missing_or_malformed_configuration_with_chinese_message(string? json, string expectedMessage)
    {
        var installRoot = CreateDirectory("install");
        if (json is not null)
        {
            File.WriteAllText(Path.Combine(installRoot, "install-location.json"), json);
        }

        var error = Assert.Throws<InvalidOperationException>(() => InstallConfiguration.Load(installRoot));
        Assert.Contains(expectedMessage, error.Message);
    }

    [Fact]
    public void RuntimeLayout_derives_install_and_data_roots()
    {
        var installRoot = CreateDirectory("app");
        var dataRoot = CreateDirectory("data");
        var layout = RuntimeLayout.Create(installRoot, dataRoot);

        Assert.Equal(Path.GetFullPath(installRoot), layout.InstallRoot);
        Assert.Equal(Path.GetFullPath(dataRoot), layout.DataRoot);
        Assert.Equal(Path.Combine(layout.InstallRoot, "runtime", "python", "python.exe"), layout.PythonExe);
        Assert.Equal(Path.Combine(layout.InstallRoot, "rag-anything-api"), layout.RagRoot);
        Assert.Equal(Path.Combine(layout.InstallRoot, "ai-tutor-system"), layout.TutorRoot);
        Assert.Equal(Path.Combine(layout.DataRoot, "logs"), layout.LogsRoot);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "webview2-user-data"), layout.WebViewUserData);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "optional-site-packages"), layout.OptionalSitePackages);
        Assert.Equal(Path.Combine(layout.DataRoot, "models", "mineru"), layout.MineruModels);
    }

    [Fact]
    public void EnsureWritableDirectories_creates_runtime_dirs_and_seed_env_files_without_overwriting()
    {
        var installRoot = CreateDirectory("install");
        var dataRoot = CreateDirectory("data");
        var ragExample = Path.Combine(installRoot, "rag-anything-api", ".env.example");
        var tutorExample = Path.Combine(installRoot, "ai-tutor-system", ".env.example");
        Directory.CreateDirectory(Path.GetDirectoryName(ragExample)!);
        Directory.CreateDirectory(Path.GetDirectoryName(tutorExample)!);
        File.WriteAllText(ragExample, "RAG_SERVICE_PORT=8003", System.Text.Encoding.UTF8);
        File.WriteAllText(tutorExample, "TUTOR_SERVICE_PORT=8002", System.Text.Encoding.UTF8);
        var layout = RuntimeLayout.Create(installRoot, dataRoot);

        layout.EnsureWritableDirectories();

        Assert.True(Directory.Exists(layout.LogsRoot));
        Assert.True(Directory.Exists(layout.WebViewUserData));
        Assert.True(Directory.Exists(layout.OptionalSitePackages));
        Assert.True(Directory.Exists(layout.MineruModels));
        Assert.Equal("RAG_SERVICE_PORT=8003", File.ReadAllText(Path.Combine(layout.ConfigRoot, "rag.env"), System.Text.Encoding.UTF8));
        Assert.Equal("TUTOR_SERVICE_PORT=8002", File.ReadAllText(Path.Combine(layout.ConfigRoot, "tutor.env"), System.Text.Encoding.UTF8));

        File.WriteAllText(Path.Combine(layout.ConfigRoot, "rag.env"), "custom=true", System.Text.Encoding.UTF8);
        layout.EnsureWritableDirectories();

        Assert.Equal("custom=true", File.ReadAllText(Path.Combine(layout.ConfigRoot, "rag.env"), System.Text.Encoding.UTF8));
    }

    [Fact]
    public void RuntimeEnvironment_builds_isolated_service_environment_without_mutating_process_environment()
    {
        var original = Environment.GetEnvironmentVariable("TEST_SYSTEM_DATA_DIR");
        var installRoot = CreateDirectory("install");
        var dataRoot = CreateDirectory("data");
        var layout = RuntimeLayout.Create(installRoot, dataRoot);
        var token = "shutdown-" + Guid.NewGuid().ToString("N");

        var environment = RuntimeEnvironment.Build(layout, token);

        Assert.Equal(original, Environment.GetEnvironmentVariable("TEST_SYSTEM_DATA_DIR"));
        Assert.Equal(layout.DataRoot, environment["TEST_SYSTEM_DATA_DIR"]);
        Assert.Equal(layout.LogsRoot, environment["TEST_SYSTEM_LOG_DIR"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "rag", "storage"), environment["TEST_SYSTEM_RAG_STORAGE_DIR"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "rag", "output"), environment["TEST_SYSTEM_RAG_OUTPUT_DIR"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "tutor_data"), environment["TEST_SYSTEM_TUTOR_DATA_DIR"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "generation_output"), environment["TEST_SYSTEM_GENERATION_OUTPUT_DIR"]);
        Assert.Equal("127.0.0.1", environment["RAG_SERVICE_HOST"]);
        Assert.Equal("8003", environment["RAG_SERVICE_PORT"]);
        Assert.Equal("127.0.0.1", environment["TUTOR_SERVICE_HOST"]);
        Assert.Equal("8002", environment["TUTOR_SERVICE_PORT"]);
        Assert.Equal("http://127.0.0.1:8003", environment["RAG_SERVICE_URL"]);
        Assert.Equal(token, environment["TEST_SYSTEM_SHUTDOWN_TOKEN"]);
        var bundledSitePackages = Path.Combine(layout.InstallRoot, "runtime", "site-packages");
        Assert.Equal(
            string.Join(Path.PathSeparator, new[] { layout.OptionalSitePackages, bundledSitePackages }),
            environment["PYTHONPATH"]);
        Assert.Equal("1", environment["PYTHONUTF8"]);
        Assert.Equal("utf-8", environment["PYTHONIOENCODING"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "pip-cache"), environment["PIP_CACHE_DIR"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "model-cache", "huggingface"), environment["HF_HOME"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "model-cache", "modelscope"), environment["MODELSCOPE_CACHE"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "model-cache", "torch"), environment["TORCH_HOME"]);
        Assert.Equal(Path.Combine(layout.DataRoot, "runtime", "torch-inductor-cache"), environment["TORCHINDUCTOR_CACHE_DIR"]);
        Assert.Equal(layout.MineruModels, environment["MINERU_MODEL_DIR"]);
        Assert.Equal(layout.PythonExe, environment["MINERU_PYTHON"]);
        Assert.Equal(Path.Combine(layout.MineruModels, "mineru.json"), environment["MINERU_TOOLS_CONFIG_JSON"]);
        Assert.StartsWith(Path.GetDirectoryName(layout.PythonExe)!, environment["PATH"], StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AppLog_writes_utf8_and_rotates_without_throwing()
    {
        var dataRoot = CreateDirectory("data");
        var log = new AppLog(dataRoot);

        log.Write("启动成功：中文日志");
        Assert.Contains("中文日志", File.ReadAllText(Path.Combine(dataRoot, "logs", "desktop-host.log"), System.Text.Encoding.UTF8));

        var active = Path.Combine(dataRoot, "logs", "desktop-host.log");
        File.WriteAllBytes(active, new byte[5 * 1024 * 1024 + 1]);
        log.Write("rotated");

        Assert.True(File.Exists(active));
        Assert.True(File.Exists(Path.Combine(dataRoot, "logs", "desktop-host.1.log")));
        Assert.True(Directory.GetFiles(Path.Combine(dataRoot, "logs"), "desktop-host.*.log").Length <= 5);
    }

    [Fact]
    public void AppLog_ignores_file_system_failures()
    {
        var dataRoot = CreateDirectory("blocked-data");
        File.WriteAllText(Path.Combine(dataRoot, "logs"), "not a directory");
        var log = new AppLog(dataRoot);

        var exception = Record.Exception(() => log.Write("should not throw"));

        Assert.Null(exception);
    }

    private string CreateDirectory(params string[] parts)
    {
        var path = Path.Combine(new[] { _root }.Concat(parts).ToArray());
        Directory.CreateDirectory(path);
        return path;
    }

    private static void WriteInstallLocation(string installRoot, object payload)
    {
        File.WriteAllText(
            Path.Combine(installRoot, "install-location.json"),
            JsonSerializer.Serialize(payload),
            System.Text.Encoding.UTF8);
    }
}
