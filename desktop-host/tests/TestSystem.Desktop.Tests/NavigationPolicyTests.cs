using TestSystem.Desktop.Web;

namespace TestSystem.Desktop.Tests;

public sealed class NavigationPolicyTests
{
    [Fact]
    public void Loopback_workspace_on_tutor_port_is_internal()
    {
        var decision = NavigationPolicy.Classify("http://127.0.0.1:8002/workspace");

        Assert.Equal(NavigationAction.AllowInternal, decision.Action);
    }

    [Theory]
    [InlineData("http://localhost:8002/generation/artifacts/download?path=generation_output%2Freport.md")]
    [InlineData("http://[::1]:8002/generation/artifacts/download?path=generation_output%2Freport.md")]
    public void Localhost_download_links_on_tutor_port_are_internal(string uri)
    {
        var decision = NavigationPolicy.Classify(uri);

        Assert.Equal(NavigationAction.AllowInternal, decision.Action);
    }

    [Theory]
    [InlineData("http://127.0.0.1:8003/workspace")]
    [InlineData("http://localhost:8003/workspace")]
    [InlineData("http://user:pass@127.0.0.1:8002/workspace")]
    [InlineData("https://127.0.0.1:8002/workspace")]
    [InlineData("http://example.com/workspace")]
    public void Non_exact_loopback_urls_are_not_internal(string uri)
    {
        var decision = NavigationPolicy.Classify(uri);

        Assert.NotEqual(NavigationAction.AllowInternal, decision.Action);
    }

    [Theory]
    [InlineData("https://example.com/docs")]
    [InlineData("http://example.com/docs")]
    public void External_http_links_open_system_browser(string uri)
    {
        var decision = NavigationPolicy.Classify(uri);

        Assert.Equal(NavigationAction.OpenExternalBrowser, decision.Action);
        Assert.Equal(uri, decision.Uri!.ToString());
    }

    [Theory]
    [InlineData("file:///C:/Windows/win.ini")]
    [InlineData("javascript:alert(1)")]
    [InlineData("data:text/html,hello")]
    [InlineData("custom:thing")]
    [InlineData("http://user:pass@example.com/")]
    public void Dangerous_or_credentialed_links_are_blocked(string uri)
    {
        var decision = NavigationPolicy.Classify(uri);

        Assert.Equal(NavigationAction.Block, decision.Action);
    }
}
