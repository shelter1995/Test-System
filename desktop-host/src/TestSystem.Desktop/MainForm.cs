using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Diagnostics;
using TestSystem.Desktop.Processes;
using TestSystem.Desktop.SingleInstance;
using TestSystem.Desktop.Startup;
using TestSystem.Desktop.Web;

namespace TestSystem.Desktop;

public partial class MainForm : Form
{
    private readonly RuntimeLayout _layout;
    private readonly IBackendSupervisor _supervisor;
    private readonly StartupCoordinator _startupCoordinator;
    private readonly SingleInstanceCoordinator _singleInstance;
    private readonly AppLog _log;
    private readonly DownloadCoordinator _downloadCoordinator;
    private bool _allowClose;
    private bool _stopping;
    private bool _launchMineruInstallerAfterClose;

    public MainForm(
        RuntimeLayout layout,
        IBackendSupervisor supervisor,
        StartupCoordinator startupCoordinator,
        SingleInstanceCoordinator singleInstance,
        AppLog log,
        DownloadCoordinator? downloadCoordinator = null)
    {
        _layout = layout;
        _supervisor = supervisor;
        _startupCoordinator = startupCoordinator;
        _singleInstance = singleInstance;
        _log = log;
        _downloadCoordinator = downloadCoordinator ?? new DownloadCoordinator(new WindowsFileSaveDialog());
        InitializeComponent();
        _singleInstance.Activated += (_, _) => RestoreAndActivate();
    }

    protected override async void OnShown(EventArgs e)
    {
        base.OnShown(e);
        await StartApplicationAsync().ConfigureAwait(true);
    }

    protected override async void OnFormClosing(FormClosingEventArgs e)
    {
        if (_allowClose)
        {
            base.OnFormClosing(e);
            return;
        }

        e.Cancel = true;
        if (_stopping)
        {
            return;
        }

        _stopping = true;
        SetStatus("正在关闭后端服务，请稍候…", showActions: false);
        Enabled = false;
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        try
        {
            await _supervisor.StopAsync(timeout.Token).ConfigureAwait(true);
        }
        catch (Exception ex) when (ex is OperationCanceledException or InvalidOperationException)
        {
            _log.Write("关闭后端服务超时或失败：" + ex.Message);
            if (_supervisor is IDisposable disposable)
            {
                disposable.Dispose();
            }
        }

        webView.Dispose();
        _singleInstance.Dispose();
        if (_launchMineruInstallerAfterClose)
        {
            LaunchMineruInstaller();
        }

        _allowClose = true;
        BeginInvoke(Close);
    }

    private async Task StartApplicationAsync()
    {
        SetStatus("正在启动 Test-System…", showActions: false);
        _log.Write("桌面宿主启动。");
        var progress = new Progress<StartupPhase>(phase => SetStatus(ToChineseStatus(phase), showActions: false));
        var result = await _startupCoordinator.StartAsync(progress).ConfigureAwait(true);
        if (!result.Ready)
        {
            _log.Write("启动失败：" + result.Error?.Detail);
            ShowStartupError(result.Error);
            return;
        }

        await InitializeWebViewAsync().ConfigureAwait(true);
    }

    private async Task InitializeWebViewAsync()
    {
        Directory.CreateDirectory(_layout.WebViewUserData);
        var environment = await CoreWebView2Environment.CreateAsync(
            browserExecutableFolder: null,
            userDataFolder: _layout.WebViewUserData).ConfigureAwait(true);
        await webView.EnsureCoreWebView2Async(environment).ConfigureAwait(true);
        ConfigureWebView();
        statusPanel.Visible = false;
        webView.Visible = true;
        webView.CoreWebView2.Navigate("http://127.0.0.1:8002/");
    }

    private void ConfigureWebView()
    {
        var settings = webView.CoreWebView2.Settings;
#if !DEBUG
        settings.AreDevToolsEnabled = false;
        settings.AreBrowserAcceleratorKeysEnabled = false;
        settings.IsStatusBarEnabled = false;
        settings.AreDefaultContextMenusEnabled = false;
#endif
        webView.CoreWebView2.NavigationStarting += (_, args) =>
        {
            var decision = NavigationPolicy.Classify(args.Uri);
            if (decision.Action == NavigationAction.AllowInternal)
            {
                return;
            }

            args.Cancel = true;
            if (decision.Action == NavigationAction.OpenExternalBrowser)
            {
                NavigationPolicy.TryOpenExternalBrowser(decision);
            }
        };
        webView.CoreWebView2.DownloadStarting += HandleDownloadStarting;
    }

    private async void HandleDownloadStarting(object? sender, CoreWebView2DownloadStartingEventArgs args)
    {
        using var deferral = args.GetDeferral();
        args.Handled = true;
        var suggestedName = Path.GetFileName(args.ResultFilePath);
        var result = await _downloadCoordinator.ResolveAsync(new DownloadRequest(suggestedName)).ConfigureAwait(true);
        if (result.Cancel)
        {
            args.Cancel = true;
            return;
        }

        args.ResultFilePath = result.ResultFilePath;
        args.DownloadOperation.StateChanged += (_, _) =>
        {
            if (args.DownloadOperation.State == CoreWebView2DownloadState.Interrupted)
            {
                _log.Write("下载失败：" + args.DownloadOperation.InterruptReason);
            }
        };
    }

    private void RetryButton_Click(object? sender, EventArgs e)
    {
        _ = StartApplicationAsync();
    }

    private void OpenLogsButton_Click(object? sender, EventArgs e)
    {
        Directory.CreateDirectory(_layout.LogsRoot);
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
        {
            FileName = _layout.LogsRoot,
            UseShellExecute = true,
        });
    }

    private void ExitButton_Click(object? sender, EventArgs e)
    {
        Close();
    }

    private void InstallMineruMenuItem_Click(object? sender, EventArgs e)
    {
        var answer = MessageBox.Show(
            "安装或修复增强解析组件需要先关闭当前后端服务，并打开独立安装窗口。是否现在重启到安装模式？",
            "安装/修复增强解析组件",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Information);
        if (answer != DialogResult.Yes)
        {
            return;
        }

        _launchMineruInstallerAfterClose = true;
        Close();
    }

    private void LaunchMineruInstaller()
    {
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
        {
            FileName = Application.ExecutablePath,
            Arguments = "--install-mineru",
            UseShellExecute = true,
        });
    }

    private void ShowStartupError(StartupError? error)
    {
        var detail = error is null
            ? "启动失败，请查看日志目录。"
            : $"{error.Summary}\r\n{error.Detail}\r\n日志目录：{error.LogDirectory}";
        SetStatus(detail, showActions: true);
    }

    private void SetStatus(string text, bool showActions)
    {
        statusLabel.Text = text;
        statusPanel.Visible = true;
        retryButton.Visible = showActions;
        openLogsButton.Visible = showActions;
        exitButton.Visible = showActions;
    }

    private void RestoreAndActivate()
    {
        if (WindowState == FormWindowState.Minimized)
        {
            WindowState = FormWindowState.Normal;
        }

        Show();
        Activate();
        BringToFront();
    }

    private static string ToChineseStatus(StartupPhase phase)
    {
        return phase switch
        {
            StartupPhase.ValidatingLayout => "正在检查安装目录…",
            StartupPhase.GuardingPorts => "正在检查服务端口…",
            StartupPhase.StartingRag => "正在启动知识库服务…",
            StartupPhase.WaitingForRag => "正在等待知识库服务就绪…",
            StartupPhase.StartingTutor => "正在启动 AI 陪练服务…",
            StartupPhase.WaitingForTutor => "正在等待前端服务就绪…",
            StartupPhase.Ready => "启动完成。",
            _ => "正在启动…",
        };
    }
}
