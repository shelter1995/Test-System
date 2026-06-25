namespace TestSystem.Desktop.Tests;

public sealed class MainFormSourceTests
{
    [Fact]
    public void WebView_is_made_visible_before_core_initialization()
    {
        var source = File.ReadAllText(FindSourceFile("desktop-host", "src", "TestSystem.Desktop", "MainForm.cs"));

        var visibleIndex = source.IndexOf("webView.Visible = true;", StringComparison.Ordinal);
        var ensureIndex = source.IndexOf("EnsureCoreWebView2Async", StringComparison.Ordinal);

        Assert.True(visibleIndex >= 0, "MainForm must show the WebView2 control before initializing it.");
        Assert.True(ensureIndex >= 0, "MainForm must initialize CoreWebView2.");
        Assert.True(
            visibleIndex < ensureIndex,
            "Hidden WebView2 controls can stall initialization; make the control visible before EnsureCoreWebView2Async.");
    }

    [Fact]
    public void Menu_and_webview_are_separated_by_layout_container()
    {
        var designer = File.ReadAllText(FindSourceFile("desktop-host", "src", "TestSystem.Desktop", "MainForm.Designer.cs"));

        Assert.Contains("private TableLayoutPanel rootLayout", designer);
        Assert.Contains("private Panel contentPanel", designer);
        Assert.Contains("rootLayout.Controls.Add(mainMenu, 0, 0)", designer);
        Assert.Contains("rootLayout.Controls.Add(contentPanel, 0, 1)", designer);
        Assert.Contains("contentPanel.Controls.Add(webView)", designer);
        Assert.Contains("contentPanel.Controls.Add(statusPanel)", designer);
        Assert.DoesNotContain("        Controls.Add(webView)", designer);
        Assert.DoesNotContain("        Controls.Add(statusPanel)", designer);
        Assert.DoesNotContain("        Controls.Add(mainMenu)", designer);
    }

    private static string FindSourceFile(params string[] relativeParts)
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var candidate = Path.Combine(new[] { directory.FullName }.Concat(relativeParts).ToArray());
            if (File.Exists(candidate))
            {
                return candidate;
            }

            directory = directory.Parent;
        }

        throw new FileNotFoundException("Unable to locate source file.", Path.Combine(relativeParts));
    }
}
