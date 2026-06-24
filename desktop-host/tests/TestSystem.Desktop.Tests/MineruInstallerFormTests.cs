using System.Windows.Forms;
using TestSystem.Desktop.Configuration;
using TestSystem.Desktop.Mineru;

namespace TestSystem.Desktop.Tests;

public sealed class MineruInstallerFormTests : IDisposable
{
    private readonly string _root;

    public MineruInstallerFormTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "test-system-mineru-form-tests", Guid.NewGuid().ToString("N"));
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
    public void Form_uses_readable_resizable_layout_for_long_status_messages()
    {
        RunSta(() =>
        {
            using var form = new MineruInstallerForm(CreateLayout(), mainAppMutexOwned: () => true);

            Assert.True(form.MinimumSize.Width >= 640);
            Assert.True(form.MinimumSize.Height >= 520);
            Assert.Equal(AutoScaleMode.Dpi, form.AutoScaleMode);
            Assert.Contains(AllControls(form), control => control is TableLayoutPanel);
            var statusBox = AllControls(form).OfType<TextBox>().Single(textBox => textBox.Name == "statusBox");
            Assert.True(statusBox.Multiline);
            Assert.True(statusBox.ReadOnly);
            Assert.Equal(ScrollBars.Vertical, statusBox.ScrollBars);
        });
    }

    [Fact]
    public void Open_log_button_has_log_path_before_installation_finishes()
    {
        RunSta(() =>
        {
            var layout = CreateLayout();
            using var form = new MineruInstallerForm(layout, mainAppMutexOwned: () => true);
            var logPathField = typeof(MineruInstallerForm).GetField("_logPath", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);

            Assert.NotNull(logPathField);
            Assert.Equal(Path.Combine(layout.LogsRoot, "mineru-installer.log"), logPathField!.GetValue(form));
        });
    }

    private RuntimeLayout CreateLayout()
    {
        var installRoot = Path.Combine(_root, "install");
        var dataRoot = Path.Combine(_root, "data");
        Directory.CreateDirectory(Path.Combine(installRoot, "runtime", "python"));
        File.WriteAllText(Path.Combine(installRoot, "runtime", "python", "python.exe"), "stub");
        Directory.CreateDirectory(dataRoot);
        return RuntimeLayout.Create(installRoot, dataRoot);
    }

    private static IEnumerable<Control> AllControls(Control root)
    {
        foreach (Control child in root.Controls)
        {
            yield return child;
            foreach (var descendant in AllControls(child))
            {
                yield return descendant;
            }
        }
    }

    private static void RunSta(Action action)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                action();
            }
            catch (Exception ex)
            {
                failure = ex;
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        if (failure is not null)
        {
            throw failure;
        }
    }
}
