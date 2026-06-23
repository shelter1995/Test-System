using TestSystem.Desktop.Configuration;

namespace TestSystem.Desktop.Mineru;

public sealed class MineruInstallerForm : Form
{
    private readonly MineruInstallerRunner _runner;
    private readonly RuntimeLayout _layout;
    private readonly ComboBox _sourceSelector = new() { Dock = DockStyle.Top, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly Label _warning = new() { Dock = DockStyle.Top, Height = 58, TextAlign = ContentAlignment.MiddleCenter };
    private readonly Label _stage = new() { Dock = DockStyle.Top, Height = 32, TextAlign = ContentAlignment.MiddleCenter };
    private readonly ProgressBar _progress = new() { Dock = DockStyle.Top, Minimum = 0, Maximum = 100 };
    private readonly Label _status = new() { Dock = DockStyle.Top, Height = 64, TextAlign = ContentAlignment.MiddleCenter };
    private readonly Button _cancel = new() { Dock = DockStyle.Bottom, Text = "取消" };
    private readonly Button _openLog = new() { Dock = DockStyle.Bottom, Text = "打开日志目录" };
    private readonly Button _startApp = new() { Dock = DockStyle.Bottom, Text = "启动智学工作台", Visible = false };
    private readonly CancellationTokenSource _cancellation = new();
    private bool _completed;
    private bool _closing;
    private string? _logPath;

    public MineruInstallerForm(RuntimeLayout layout, Func<bool>? mainAppMutexOwned = null)
    {
        _layout = layout;
        _runner = new MineruInstallerRunner(layout, mainAppMutexOwned: mainAppMutexOwned);
        Text = "安装/修复增强解析组件";
        Size = new Size(560, 360);
        _sourceSelector.Items.AddRange(["ModelScope（推荐）", "Hugging Face"]);
        _sourceSelector.SelectedIndex = 0;
        _warning.Text = "将联网下载 MinerU 依赖和 Pipeline 模型，并占用额外磁盘空间。网络不稳定时可稍后重试。";
        Controls.Add(_status);
        Controls.Add(_progress);
        Controls.Add(_stage);
        Controls.Add(_warning);
        Controls.Add(_sourceSelector);
        Controls.Add(_startApp);
        Controls.Add(_openLog);
        Controls.Add(_cancel);
        _cancel.Click += (_, _) =>
        {
            if (_completed)
            {
                Close();
            }
            else
            {
                _cancellation.Cancel();
            }
        };
        _startApp.Click += (_, _) =>
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = Path.Combine(_layout.InstallRoot, "TestSystem.exe"),
                UseShellExecute = true,
            });
            Close();
        };
        _openLog.Click += (_, _) =>
        {
            if (_logPath is not null)
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = Path.GetDirectoryName(_logPath)!,
                    UseShellExecute = true,
                });
            }
        };
    }

    protected override async void OnShown(EventArgs e)
    {
        base.OnShown(e);
        _status.Text = "正在安装增强解析组件…";
        _stage.Text = "准备安装";
        _sourceSelector.Enabled = false;
        var result = await _runner.StartAsync(
            SelectedSource,
            new Progress<MineruInstallProgress>(item =>
            {
                if (_closing || IsDisposed)
                {
                    return;
                }

                _progress.Value = Math.Clamp(item.Percent, 0, 100);
                _stage.Text = item.Stage;
                _status.Text = item.Message;
            }),
            _cancellation.Token).ConfigureAwait(true);
        if (_closing || IsDisposed)
        {
            return;
        }

        _logPath = result.LogPath;
        _status.Text = result.Success ? "增强解析组件安装完成。" : result.Message;
        _stage.Text = result.Success ? "complete" : "failed";
        _completed = true;
        _cancel.Text = "关闭";
        _startApp.Visible = result.Success;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _closing = true;
        _cancellation.Cancel();
        _cancellation.Dispose();
        base.OnFormClosing(e);
    }

    private MineruModelSource SelectedSource => _sourceSelector.SelectedIndex == 1
        ? MineruModelSource.HuggingFace
        : MineruModelSource.ModelScope;
}
