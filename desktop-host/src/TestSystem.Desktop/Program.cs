namespace TestSystem.Desktop;

using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Diagnostics;
using TestSystem.Desktop.Mineru;
using TestSystem.Desktop.Processes;
using TestSystem.Desktop.SingleInstance;
using TestSystem.Desktop.Startup;
using TestSystem.Desktop.Uninstall;

public enum ApplicationStartupMode
{
    MainApp,
    MineruInstaller,
    DataDeletion,
}

public static class Program
{
    private static readonly Guid ProductId = Guid.Parse("D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D");

    /// <summary>
    ///  The main entry point for the application.
    /// </summary>
    [STAThread]
    public static ApplicationStartupMode SelectStartupMode(string[] args)
    {
        if (args.Any(arg => string.Equals(arg, "--delete-data", StringComparison.OrdinalIgnoreCase)))
        {
            return ApplicationStartupMode.DataDeletion;
        }

        if (args.Any(arg => string.Equals(arg, "--install-mineru", StringComparison.OrdinalIgnoreCase)))
        {
            return ApplicationStartupMode.MineruInstaller;
        }

        return ApplicationStartupMode.MainApp;
    }

    static int Main(string[] args)
    {
        try
        {
            var startupMode = SelectStartupMode(args);
            if (startupMode == ApplicationStartupMode.DataDeletion)
            {
                return RunDataDeletion(args);
            }

            ApplicationConfiguration.Initialize();
            if (startupMode == ApplicationStartupMode.MineruInstaller)
            {
                var mineruInstall = InstallConfiguration.Load(AppContext.BaseDirectory);
                var mineruLayout = RuntimeLayout.Create(mineruInstall.InstallRoot, mineruInstall.DataDir);
                mineruLayout.EnsureWritableDirectories();
                Application.Run(new MineruInstallerForm(
                    mineruLayout,
                    mainAppMutexOwned: () => SingleInstanceCoordinator.IsPrimaryInstanceRunning(ProductId)));
                return 0;
            }

            using var singleInstance = SingleInstanceCoordinator.Create(ProductId);
            if (!singleInstance.IsPrimary)
            {
                return singleInstance.SignalExistingInstanceAsync().GetAwaiter().GetResult();
            }

            singleInstance.StartActivationServerAsync().GetAwaiter().GetResult();
            var installRoot = AppContext.BaseDirectory;
            var install = InstallConfiguration.Load(installRoot);
            var layout = RuntimeLayout.Create(install.InstallRoot, install.DataDir);
            layout.EnsureWritableDirectories();
            var log = new AppLog(layout.DataRoot);
            var shutdownToken = Guid.NewGuid().ToString("N");
            var environment = RuntimeEnvironment.Build(layout, shutdownToken);
            using var supervisor = new BackendProcessSupervisor(layout, environment, shutdownToken);
            using var healthProbe = new HttpHealthProbe();
            var startup = new StartupCoordinator(layout, supervisor, healthProbe);
            Application.Run(new MainForm(layout, supervisor, startup, singleInstance, log));
            return 0;
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            MessageBox.Show(ex.Message, "智学工作台启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static int RunDataDeletion(string[] args)
    {
        try
        {
            var dataDir = GetRequiredArgument(args, "--delete-data");
            var installIdText = GetRequiredArgument(args, "--install-id");
            if (!Guid.TryParse(installIdText, out var installId))
            {
                throw new InvalidOperationException("安装标识无效。");
            }

            DataDeletionGuard.DeleteDataDirectory(dataDir, installId, AppContext.BaseDirectory);
            return 0;
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            LogDataDeletionFailure(ex);
            return 1;
        }
    }

    private static string GetRequiredArgument(string[] args, string name)
    {
        for (var index = 0; index < args.Length - 1; index++)
        {
            if (string.Equals(args[index], name, StringComparison.OrdinalIgnoreCase))
            {
                return args[index + 1];
            }
        }

        throw new InvalidOperationException($"缺少参数：{name}");
    }

    private static void LogDataDeletionFailure(Exception ex)
    {
        try
        {
            var logPath = Path.Combine(Path.GetTempPath(), "ZhiXueWorkbench-delete-data.log");
            File.AppendAllText(
                logPath,
                $"[{DateTimeOffset.Now:O}] {ex}{Environment.NewLine}",
                System.Text.Encoding.UTF8);
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
