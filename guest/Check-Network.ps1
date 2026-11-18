$ErrorActionPreference='Stop'
function Test-Tcp([string]$Address,[int]$Port) {
 $client=New-Object Net.Sockets.TcpClient
 try {
  $task=$client.ConnectAsync($Address,$Port)
  if (!$task.Wait(4000)) { return $false }
  return $client.Connected
 } catch { return $false } finally { $client.Dispose() }
}
[ordered]@{
 ComputerName=$env:COMPUTERNAME
 Addresses=@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress)
 Routes=@(Get-NetRoute -AddressFamily IPv4 | Where-Object DestinationPrefix -eq '0.0.0.0/0' | Select-Object NextHop,InterfaceAlias)
 ExternalTcp443=(Test-Tcp '1.1.1.1' 443)
} | ConvertTo-Json -Depth 4
