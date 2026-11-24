# Read-only inventory for the ORN Alpine portability experiment.
# Run from any directory with: powershell -ExecutionPolicy Bypass -File .\scripts\alpine_orn_host_inventory.ps1

$ErrorActionPreference = "Continue"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot

try {
    Write-Output "=== ORN ALPINE HOST INVENTORY ==="
    Write-Output ("Timestamp: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"))
    Write-Output ("Repository: {0}" -f $repoRoot)

    Write-Output "`n--- CPU ---"
    Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed |
        Format-List

    Write-Output "--- Windows / RAM ---"
    $os = Get-CimInstance Win32_OperatingSystem
    [pscustomobject]@{
        Windows = $os.Caption
        Version = $os.Version
        Build = $os.BuildNumber
        RAM_Total_GiB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        RAM_Free_GiB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    } | Format-List

    Write-Output "--- Host volume ---"
    $driveName = (Get-Item $repoRoot).PSDrive.Name
    Get-PSDrive -Name $driveName |
        Select-Object Name,
            @{Name="Used_GiB";Expression={[math]::Round($_.Used / 1GB, 2)}},
            @{Name="Free_GiB";Expression={[math]::Round($_.Free / 1GB, 2)}} |
        Format-List

    Write-Output "--- Hypervisor ---"
    Get-CimInstance Win32_ComputerSystem |
        Select-Object Manufacturer, Model, HypervisorPresent |
        Format-List

    Write-Output "--- QEMU ---"
    $qemuFromPath = Get-Command qemu-system-x86_64.exe -ErrorAction SilentlyContinue
    $qemuCandidates = @()
    if ($qemuFromPath) { $qemuCandidates += $qemuFromPath.Source }
    $qemuCandidates += @(
        "C:\Program Files\qemu\qemu-system-x86_64.exe",
        "C:\Program Files (x86)\qemu\qemu-system-x86_64.exe",
        "C:\qemu\qemu-system-x86_64.exe",
        (Join-Path $HOME "qemu\qemu-system-x86_64.exe"),
        (Join-Path $repoRoot ".doxoade\opt\qemu\qemu-system-x86_64.exe")
    )
    $qemuExe = $qemuCandidates |
        Where-Object { $_ -and (Test-Path $_) } |
        Select-Object -First 1

    if ($qemuExe) {
        Write-Output ("QEMU executable: {0}" -f $qemuExe)
        & $qemuExe --version
        $qemuImg = Join-Path (Split-Path $qemuExe -Parent) "qemu-img.exe"
    } else {
        Write-Warning "qemu-system-x86_64.exe não encontrado nos caminhos conhecidos."
        $qemuImg = $null
    }

    Write-Output "--- QCOW2 ---"
    $disk = Join-Path $repoRoot "data\sandbox\alpine.img.qcow2"
    if (Test-Path $disk) {
        Get-Item $disk |
            Select-Object FullName,
                @{Name="Physical_Size_MiB";Expression={[math]::Round($_.Length / 1MB, 2)}} |
            Format-List
        if ($qemuImg -and (Test-Path $qemuImg)) {
            & $qemuImg info $disk
        } else {
            Write-Warning "qemu-img.exe não encontrado ao lado do QEMU."
        }
    } else {
        Write-Warning ("Imagem não encontrada: {0}" -f $disk)
    }

    Write-Output "--- Git HEAD ---"
    git rev-parse HEAD

    Write-Output "--- QEMU daemon log (tail 35) ---"
    $daemonLog = Join-Path $repoRoot "data\sandbox\daemon.log"
    if (Test-Path $daemonLog) {
        Get-Content $daemonLog -Tail 35
    } else {
        Write-Output "daemon.log ausente."
    }

    Write-Output "=== END INVENTORY ==="
}
finally {
    Pop-Location
}
