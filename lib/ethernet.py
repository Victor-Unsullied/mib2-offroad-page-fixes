"""Check the Windows route and local Ethernet port used for the head unit."""

from ipaddress import IPv4Address
import json
import subprocess
import sys


_QUERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$selection = @(Find-NetRoute -RemoteIPAddress '__TARGET__')
$route = $selection | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_NetRoute' } | Select-Object -First 1
$source = $selection | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_NetIPAddress' } | Select-Object -First 1
if (!$route -or !$source -or $route.NextHop -ne '0.0.0.0' -or $route.InterfaceIndex -ne $source.InterfaceIndex) {
    Write-Output '{}'
    exit
}
$adapter = Get-NetAdapter -Physical | Where-Object { $_.ifIndex -eq $route.InterfaceIndex } | Select-Object -First 1
# NdisPhysicalMedium 14 is IEEE 802.3 (wired Ethernet).
if (!$adapter -or $adapter.Status -ne 'Up' -or $adapter.NdisPhysicalMedium -ne 14) {
    Write-Output '{}'
    exit
}
[pscustomobject]@{ name = $adapter.Name; address = $source.IPAddress } | ConvertTo-Json -Compress
'''


def wired_route(host):
    """Return the selected Ethernet port and source IP on Windows, or None elsewhere."""
    if sys.platform != 'win32':
        return None
    command = _QUERY.replace('__TARGET__', str(IPv4Address(host)))
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
            capture_output=True, check=True, encoding='utf-8', timeout=12,
        )
        route = json.loads(result.stdout)
        name = route['name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Missing Ethernet port name')
        return name, IPv4Address(route['address'])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise ValueError('Could not verify a direct Windows Ethernet connection') from error
