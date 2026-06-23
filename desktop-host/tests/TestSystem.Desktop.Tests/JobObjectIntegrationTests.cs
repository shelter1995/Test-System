using System.Diagnostics;
using TestSystem.Desktop.Processes;

namespace TestSystem.Desktop.Tests;

public sealed class JobObjectIntegrationTests
{
    [Fact]
    public void Disposing_job_object_terminates_assigned_child_process()
    {
        using var process = Process.Start(new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = "/c ping -t 127.0.0.1 > nul",
            UseShellExecute = false,
            CreateNoWindow = true,
        })!;
        Assert.False(process.HasExited);

        using (var job = new WindowsJobObject())
        {
            job.Assign(process);
        }

        Assert.True(process.WaitForExit(milliseconds: 5000));
    }
}
