using Microsoft.Web.WebView2.WinForms;

namespace TestSystem.Desktop;

public partial class MainForm
{
    private WebView2 webView = null!;
    private Panel statusPanel = null!;
    private Label statusLabel = null!;
    private Button retryButton = null!;
    private Button openLogsButton = null!;
    private Button exitButton = null!;

    private void InitializeComponent()
    {
        webView = new WebView2();
        statusPanel = new Panel();
        statusLabel = new Label();
        retryButton = new Button();
        openLogsButton = new Button();
        exitButton = new Button();
        ((System.ComponentModel.ISupportInitialize)webView).BeginInit();
        statusPanel.SuspendLayout();
        SuspendLayout();

        webView.AllowExternalDrop = false;
        webView.CreationProperties = null;
        webView.DefaultBackgroundColor = Color.White;
        webView.Dock = DockStyle.Fill;
        webView.Location = new Point(0, 0);
        webView.Name = "webView";
        webView.Size = new Size(1184, 761);
        webView.TabIndex = 0;
        webView.Visible = false;
        webView.ZoomFactor = 1D;

        statusPanel.Controls.Add(exitButton);
        statusPanel.Controls.Add(openLogsButton);
        statusPanel.Controls.Add(retryButton);
        statusPanel.Controls.Add(statusLabel);
        statusPanel.Dock = DockStyle.Fill;
        statusPanel.Location = new Point(0, 0);
        statusPanel.Name = "statusPanel";
        statusPanel.Padding = new Padding(32);
        statusPanel.Size = new Size(1184, 761);
        statusPanel.TabIndex = 1;

        statusLabel.Anchor = AnchorStyles.None;
        statusLabel.AutoSize = false;
        statusLabel.Font = new Font("Microsoft YaHei UI", 11F);
        statusLabel.Location = new Point(292, 274);
        statusLabel.Name = "statusLabel";
        statusLabel.Size = new Size(600, 120);
        statusLabel.TabIndex = 0;
        statusLabel.Text = "正在启动 Test-System…";
        statusLabel.TextAlign = ContentAlignment.MiddleCenter;

        retryButton.Anchor = AnchorStyles.None;
        retryButton.Location = new Point(394, 420);
        retryButton.Name = "retryButton";
        retryButton.Size = new Size(120, 36);
        retryButton.TabIndex = 1;
        retryButton.Text = "重试";
        retryButton.UseVisualStyleBackColor = true;
        retryButton.Visible = false;
        retryButton.Click += RetryButton_Click;

        openLogsButton.Anchor = AnchorStyles.None;
        openLogsButton.Location = new Point(532, 420);
        openLogsButton.Name = "openLogsButton";
        openLogsButton.Size = new Size(120, 36);
        openLogsButton.TabIndex = 2;
        openLogsButton.Text = "打开日志目录";
        openLogsButton.UseVisualStyleBackColor = true;
        openLogsButton.Visible = false;
        openLogsButton.Click += OpenLogsButton_Click;

        exitButton.Anchor = AnchorStyles.None;
        exitButton.Location = new Point(670, 420);
        exitButton.Name = "exitButton";
        exitButton.Size = new Size(120, 36);
        exitButton.TabIndex = 3;
        exitButton.Text = "退出";
        exitButton.UseVisualStyleBackColor = true;
        exitButton.Visible = false;
        exitButton.Click += ExitButton_Click;

        AutoScaleDimensions = new SizeF(7F, 17F);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(1184, 761);
        Controls.Add(webView);
        Controls.Add(statusPanel);
        MinimumSize = new Size(960, 640);
        Name = "MainForm";
        StartPosition = FormStartPosition.CenterScreen;
        Text = "Test-System";
        ((System.ComponentModel.ISupportInitialize)webView).EndInit();
        statusPanel.ResumeLayout(false);
        ResumeLayout(false);
    }
}
