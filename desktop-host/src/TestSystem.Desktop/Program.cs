namespace TestSystem.Desktop;

using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Diagnostics;
using TestSystem.Desktop.Processes;
using TestSystem.Desktop.SingleInstance;
using TestSystem.Desktop.Startup;

static class Program
{
    private static readonly Guid ProductId = Guid.Parse("D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D");

    /// <summary>
    ///  The main entry point for the application.
    /// </summary>
    [STAThread]
    static int Main()
    {
        ApplicationConfiguration.Initialize();
        try
        {
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
