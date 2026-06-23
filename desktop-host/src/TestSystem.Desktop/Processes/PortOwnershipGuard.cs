using System.Net;
using System.Net.Sockets;

namespace TestSystem.Desktop.Processes;

public interface IPortOwnershipGuard
{
    void EnsureAvailable(params (string ServiceName, int Port)[] ports);
}

public sealed class PortOwnershipGuard : IPortOwnershipGuard
{
    public void EnsureAvailable(params (string ServiceName, int Port)[] ports)
    {
        foreach (var (serviceName, port) in ports)
        {
            try
            {
                using var listener = new TcpListener(IPAddress.Loopback, port);
                listener.Server.ExclusiveAddressUse = true;
                listener.Start();
            }
            catch (SocketException ex)
            {
                throw new InvalidOperationException($"{serviceName} 端口 {port} 已被占用，请关闭占用该端口的程序后重试。", ex);
            }
        }
    }
}
