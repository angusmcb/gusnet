
$ErrorActionPreference = 'Stop'

$toolsDir = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)"
$FolderOfPackage = Split-Path -Parent $toolsDir

$NewRelease = $env:ChocolateyPackageVersion
$LTRversion = '3.44.1'

$DownloadUrl = 'https://qgis.org/downloads/windows/QGIS-OSGeo4W-3.34.1-2.msi'
$Checksum = '3c321cdbd0951119d5ab3058b208527b90b77227db6306b428601bd6868dcc9c'

# Replace Get-PackageParameters
$KeepOldVersions = $false

# Replace Get-UninstallRegistryKey with native PowerShell
function Get-InstalledQGIS {
    $UninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    Get-ItemProperty $UninstallKeys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "QGIS *" } |
        Select-Object DisplayName, UninstallString, PSPath
}

[array]$Keys = Get-InstalledQGIS

if ($Keys) {
    $TargetKey = $null
    if ($Keys.Count -gt 1) {
        Write-Warning "Multiple, previously-installed versions of QGIS found."
        $TargetVersion = [version]'0.0'
        Foreach ($key in $Keys) {
            $v = [version]($key.DisplayName -replace '[^0-9.]','')
            if ($v -ge $TargetVersion) {
                $TargetVersion = $v
                $TargetKey = $key
            }
        }
    } elseif ($Keys.Count -eq 1) {
        $TargetKey = $Keys[0]
        $TargetVersion = [version]($TargetKey.DisplayName -replace '[^0-9.]','')
        Write-Verbose "QGIS version, $TargetVersion, already installed."
    }

    $PkgShortVersion = [version](([version]$env:ChocolateyPackageVersion).tostring(2))

    If ($TargetVersion -le [version]$LTRversion) {
        if (Test-Path ($FolderOfPackage + "-ltr")) {
            $nuspec = Get-ChildItem ($FolderOfPackage + "-ltr") -Filter "*.nuspec" | Select-Object -First 1
            $text = (Get-Content $nuspec.fullname | Select-String '<version>[0-9.]*</version>').Matches.Value
            $LTRPkgShortVer = [version](([version]($text -replace '[^0-9.]','')).ToString(2))
            if ($LTRPkgShortVer -ge [version]($TargetVersion.tostring(2))) {
                $TargetKey = $null
                If ($LTRPkgShortVer -ge $PkgShortVersion) {
                    Throw ("QGIS package must be newer than any QGIS-LTR package installed!`n" +
                            "`tInstalled QGIS-LTR version:  $LTRPkgShortVer.x`n")
                }
            }
        }
    }
}

if ($TargetKey) {
    $TargetShortVersion = [version](([version]$TargetVersion).tostring(2))

    if ($KeepOldVersions) {
        Write-Host "You have requested for this package to NOT uninstall any previous installs of QGIS." -ForegroundColor Cyan
    }

    if ((-not $KeepOldVersions) -or ($TargetShortVersion -eq $PkgShortVersion)) {
        if ($KeepOldVersions) {
            Write-Warning "Multiple installs of minor (xx.yy) releases are not possible. Version $TargetVersion will be uninstalled."
        }
        Write-Host "Uninstalling older QGIS version $TargetVersion. Please wait." -ForegroundColor Cyan

        # Clean up registry
        Get-ChildItem HKLM:\SOFTWARE |
            Where-Object {$_.name -match "QGIS ?$TargetShortVersion"} |
            Remove-Item -Recurse -Force

        # Clean up desktop shortcuts
        if (Test-Path "$env:PUBLIC\Desktop\QGIS $TargetShortVersion") {
            Remove-Item "$env:PUBLIC\Desktop\QGIS $TargetShortVersion" -Recurse -Force
        }

        $OrphanedLinks = Get-ChildItem "$env:PUBLIC\Desktop\" -Filter "*.lnk" -ErrorAction SilentlyContinue
        Foreach ($Item in $OrphanedLinks) {
            $LinkTarget = (New-Object -ComObject Wscript.Shell).CreateShortcut($Item.FullName).TargetPath
            if ($LinkTarget -match "QGIS $TargetShortVersion") {
                Remove-Item $Item.FullName -Recurse -Force
            }
        }

        # Uninstall
        if ($TargetKey.UninstallString -match '\.exe$') {
            $exeToRun = $TargetKey.UninstallString
            $Switches = '/S'
        } else {
            $exeToRun = 'msiexec.exe'
            $ID = ($TargetKey.UninstallString -split '/x')[-1]
            $Switches = "/x$ID /qn /norestart"
        }

        # Replace Start-ChocolateyProcessAsAdmin with native Start-Process
        Start-Process -FilePath $exeToRun -ArgumentList $Switches -Wait -NoNewWindow

        # Wait for cleanup
        Get-Process | Where-Object {$_.path -match '.*Temp.*chocolatey.*Au_.exe'} | Wait-Process
    }
}

# Install QGIS
Write-Host "Installing QGIS can take a few minutes. Please be patient." -ForegroundColor Cyan

$InstallerPath = Join-Path $env:TEMP "qgis-installer.msi"

# Download the MSI
Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath

# Verify checksum
$ActualChecksum = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash
if ($ActualChecksum -ne $Checksum) {
    throw "Checksum mismatch! Expected: $Checksum, Got: $ActualChecksum"
}

# Install
$InstallArgs = @(
    '/i', $InstallerPath
    '/qn'
    '/norestart'
    '/l*v', "$env:TEMP\qgis-install.log"
)

Start-Process -FilePath 'msiexec.exe' -ArgumentList $InstallArgs -Wait -NoNewWindow

# Cleanup
Remove-Item $InstallerPath -Force

Write-Host "QGIS installation complete!" -ForegroundColor Green
