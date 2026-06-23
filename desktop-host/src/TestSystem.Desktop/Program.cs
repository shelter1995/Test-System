namespace TestSystem.Desktop;

using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Diagnostics;
using TestSystem.Desktop.Mineru;
using TestSystem.Desktop.Processes;
using TestSystem.Desktop.SingleInstance;
using TestSystem.Desktop.Startup;

public enum ApplicationStartupMode
{
    MainApp,
    MineruInstaller,
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
        return args.Any(arg => string.Equals(arg, "--install-mineru", StringComparison.OrdinalIgnoreCase))
            ? ApplicationStartupMode.MineruInstaller
            : ApplicationStartupMode.MainApp;
    }

    static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            if (SelectStartupMode(args) == ApplicationStartupMode.MineruInstaller)
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
            MessageBox.Show(ex.Message, "Test-System 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
