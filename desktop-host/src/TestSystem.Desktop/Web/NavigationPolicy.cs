using System.Diagnostics;

namespace TestSystem.Desktop.Web;

public enum NavigationAction
{
    AllowInternal,
    OpenExternalBrowser,
    Block,
}

public sealed record NavigationDecision(NavigationAction Action, Uri? Uri = null)
{
    public static NavigationDecision Internal(Uri uri)
    {
        return new NavigationDecision(NavigationAction.AllowInternal, uri);
    }

    public static NavigationDecision External(Uri uri)
    {
        return new NavigationDecision(NavigationAction.OpenExternalBrowser, uri);
    }

    public static NavigationDecision Blocked(Uri? uri = null)
    {
        return new NavigationDecision(NavigationAction.Block, uri);
    }
}

public static class NavigationPolicy
{
    private const int InternalTutorPort = 8002;

    public static NavigationDecision Classify(string uriText)
    {
        if (!Uri.TryCreate(uriText, UriKind.Absolute, out var uri))
        {
            return NavigationDecision.Blocked();
        }

        if (!string.IsNullOrEmpty(uri.UserInfo))
        {
            return NavigationDecision.Blocked(uri);
        }

        if (IsInternal(uri))
        {
            return NavigationDecision.Internal(uri);
        }

        if (string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            || string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            if (IsLocalHost(uri))
            {
                return NavigationDecision.Blocked(uri);
            }

            return NavigationDecision.External(uri);
        }

        return NavigationDecision.Blocked(uri);
    }

    public static bool TryOpenExternalBrowser(NavigationDecision decision)
    {
        if (decision.Action != NavigationAction.OpenExternalBrowser || decision.Uri is null)
        {
            return false;
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = decision.Uri.ToString(),
            UseShellExecute = true,
        });
        return true;
    }

    private static bool IsInternal(Uri uri)
    {
        return string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            && IsLocalHost(uri)
            && uri.Port == InternalTutorPort
            && string.IsNullOrEmpty(uri.UserInfo);
    }

    private static bool IsLocalHost(Uri uri)
    {
        return string.Equals(uri.Host, "127.0.0.1", StringComparison.OrdinalIgnoreCase)
            || string.Equals(uri.Host, "[::1]", StringComparison.OrdinalIgnoreCase)
            || string.Equals(uri.Host, "::1", StringComparison.OrdinalIgnoreCase)
            || string.Equals(uri.Host, "localhost", StringComparison.OrdinalIgnoreCase);
    }
}
