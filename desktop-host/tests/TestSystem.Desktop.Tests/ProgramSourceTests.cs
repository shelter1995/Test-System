namespace TestSystem.Desktop.Tests;

public sealed class ProgramSourceTests
{
    [Fact]
    public void Main_entry_point_is_marked_sta_for_winforms_and_webview2()
    {
        var source = File.ReadAllText(FindSourceFile("desktop-host", "src", "TestSystem.Desktop", "Program.cs"));
        var mainIndex = source.IndexOf("static int Main(string[] args)", StringComparison.Ordinal);
        Assert.True(mainIndex >= 0, "Program.Main entry point must exist.");

        var beforeMain = source[..mainIndex];
        var lastStaIndex = beforeMain.LastIndexOf("[STAThread]", StringComparison.Ordinal);
        Assert.True(lastStaIndex >= 0, "Program.Main must be marked with [STAThread].");

        var textBetweenStaAndMain = beforeMain[lastStaIndex..];
        Assert.DoesNotContain("SelectStartupMode", textBetweenStaAndMain);
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
