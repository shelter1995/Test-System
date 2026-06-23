using System.Security.Principal;
using TestSystem.Desktop.SingleInstance;

namespace TestSystem.Desktop.Tests;

public sealed class SingleInstanceTests
{
    [Fact]
    public void Mutex_name_contains_current_user_sid_and_product_guid()
    {
        var productId = Guid.NewGuid();
        var names = SingleInstanceCoordinator.BuildNames(productId);
        var sid = WindowsIdentity.GetCurrent().User!.Value;

        Assert.Contains(sid, names.MutexName);
        Assert.Contains(productId.ToString("D"), names.MutexName);
        Assert.Contains(sid, names.PipeName);
        Assert.Contains(productId.ToString("D"), names.PipeName);
    }

    [Fact]
    public async Task First_instance_owns_mutex_second_sends_activation_and_first_receives_it()
    {
        var productId = Guid.NewGuid();
        using var first = SingleInstanceCoordinator.Create(productId);
        var received = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        first.Activated += (_, _) => received.TrySetResult();

        Assert.True(first.IsPrimary);
        await first.StartActivationServerAsync();

        using var second = SingleInstanceCoordinator.Create(productId);

        Assert.False(second.IsPrimary);
        Assert.Equal(0, await second.SignalExistingInstanceAsync());
        await received.Task.WaitAsync(TimeSpan.FromSeconds(5));
    }
}
