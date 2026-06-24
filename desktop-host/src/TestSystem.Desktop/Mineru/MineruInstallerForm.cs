using TestSystem.Desktop.Configuration;

namespace TestSystem.Desktop.Mineru;

public sealed class MineruInstallerForm : Form
{
    private readonly MineruInstallerRunner _runner;
    private readonly RuntimeLayout _layout;
    private readonly ComboBox _sourceSelector = new() { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly Label _warning = new() { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter };
    private readonly Label _stage = new() { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter };
    private readonly ProgressBar _progress = new() { Dock = DockStyle.Fill, Minimum = 0, Maximum = 100 };
    private readonly TextBox _status = new()
    {
        Name = "statusBox",
        Dock = DockStyle.Fill,
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        BorderStyle = BorderStyle.FixedSingle,
        TextAlign = HorizontalAlignment.Center,
    };
    private readonly Button _cancel = new() { Text = "取消", Width = 132, Height = 34 };
    private readonly Button _openLog = new() { Text = "打开日志目录", Width = 132, Height = 34 };
    private readonly Button _startApp = new() { Text = "启动智学工作台", Width = 132, Height = 34, Visible = false };
    private readonly CancellationTokenSource _cancellation = new();
    private bool _completed;
    private bool _closing;
    private string? _logPath;

    public MineruInstallerForm(RuntimeLayout layout, Func<bool>? mainAppMutexOwned = null)
    {
        _layout = layout;
        _runner = new MineruInstallerRunner(layout, mainAppMutexOwned: mainAppMutexOwned);
        Text = "安装/修复增强解析组件";
        AutoScaleMode = AutoScaleMode.Dpi;
        MinimumSize = new Size(640, 520);
        Size = new Size(720, 560);
        StartPosition = FormStartPosition.CenterScreen;
        _logPath = Path.Combine(_layout.LogsRoot, "mineru-installer.log");
        _sourceSelector.Items.AddRange(["ModelScope（推荐）", "Hugging Face"]);
        _sourceSelector.SelectedIndex = 0;
        _warning.Text = "将联网下载 MinerU、Pipeline 模型、FFmpeg 和 Whisper，用于增强文档/OCR/音视频解析，并占用额外磁盘空间。网络不稳定时可稍后重试。";
        Controls.Add(BuildLayout());
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
            try
            {
                Directory.CreateDirectory(_layout.LogsRoot);
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = Path.GetDirectoryName(_logPath!) ?? _layout.LogsRoot,
                    UseShellExecute = true,
                });
            }
            catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception or IOException or UnauthorizedAccessException)
            {
                MessageBox.Show(
                    "无法打开日志目录：\r\n" + _layout.LogsRoot + "\r\n\r\n" + ex.Message,
                    "打开日志目录失败",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }
        };
    }

    private TableLayoutPanel BuildLayout()
    {
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(14),
            ColumnCount = 1,
            RowCount = 6,
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 70));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            WrapContents = false,
            Padding = new Padding(0, 10, 0, 0),
        };
        buttons.Controls.Add(_cancel);
        buttons.Controls.Add(_openLog);
        buttons.Controls.Add(_startApp);

        layout.Controls.Add(_sourceSelector, 0, 0);
        layout.Controls.Add(_warning, 0, 1);
        layout.Controls.Add(_stage, 0, 2);
        layout.Controls.Add(_progress, 0, 3);
        layout.Controls.Add(_status, 0, 4);
        layout.Controls.Add(buttons, 0, 5);
        return layout;
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
