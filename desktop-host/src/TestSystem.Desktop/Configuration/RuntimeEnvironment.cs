namespace TestSystem.Desktop.Configuration;

public static class RuntimeEnvironment
{
    public static IReadOnlyDictionary<string, string> Build(RuntimeLayout layout, string shutdownToken)
    {
        ArgumentNullException.ThrowIfNull(layout);
        if (string.IsNullOrWhiteSpace(shutdownToken))
        {
            throw new InvalidOperationException("关闭令牌不能为空。");
        }

        var env = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["TEST_SYSTEM_DATA_DIR"] = layout.DataRoot,
            ["TEST_SYSTEM_LOG_DIR"] = layout.LogsRoot,
            ["TEST_SYSTEM_RAG_STORAGE_DIR"] = Path.Combine(layout.DataRoot, "rag", "storage"),
            ["TEST_SYSTEM_RAG_OUTPUT_DIR"] = Path.Combine(layout.DataRoot, "rag", "output"),
            ["TEST_SYSTEM_TUTOR_DATA_DIR"] = Path.Combine(layout.DataRoot, "tutor_data"),
            ["TEST_SYSTEM_GENERATION_OUTPUT_DIR"] = Path.Combine(layout.DataRoot, "generation_output"),
            ["TEST_SYSTEM_SHUTDOWN_TOKEN"] = shutdownToken,
            ["RAG_SERVICE_HOST"] = "127.0.0.1",
            ["RAG_SERVICE_PORT"] = "8003",
            ["TUTOR_SERVICE_HOST"] = "127.0.0.1",
            ["TUTOR_SERVICE_PORT"] = "8002",
            ["RAG_SERVICE_URL"] = "http://127.0.0.1:8003",
            ["PYTHONHOME"] = Path.GetDirectoryName(layout.PythonExe)!,
            ["PYTHONPATH"] = layout.OptionalSitePackages,
            ["PYTHONNOUSERSITE"] = "1",
            ["PYTHONUTF8"] = "1",
            ["PYTHONIOENCODING"] = "utf-8",
            ["PIP_CACHE_DIR"] = Path.Combine(layout.RuntimeRoot, "pip-cache"),
            ["HF_HOME"] = Path.Combine(layout.RuntimeRoot, "model-cache", "huggingface"),
            ["TRANSFORMERS_CACHE"] = Path.Combine(layout.RuntimeRoot, "model-cache", "huggingface"),
            ["MODELSCOPE_CACHE"] = Path.Combine(layout.RuntimeRoot, "model-cache", "modelscope"),
            ["MINERU_MODEL_DIR"] = layout.MineruModels,
            ["PATH"] = BuildPath(layout),
        };

        return env;
    }

    private static string BuildPath(RuntimeLayout layout)
    {
        var entries = new List<string>
        {
            Path.GetDirectoryName(layout.PythonExe)!,
            Path.Combine(Path.GetDirectoryName(layout.PythonExe)!, "Scripts"),
            Path.Combine(layout.ToolsRoot, "ffmpeg", "bin"),
            Path.Combine(layout.ToolsRoot, "libreoffice"),
        };

        var existingPath = Environment.GetEnvironmentVariable("PATH");
        if (!string.IsNullOrWhiteSpace(existingPath))
        {
            entries.Add(existingPath);
        }

        return string.Join(Path.PathSeparator, entries.Where(item => !string.IsNullOrWhiteSpace(item)));
    }
}
