<#
.SYNOPSIS
Docker Desktop (Windows) が残留 Unix ソケットで起動不能になるループから復旧する。

.DESCRIPTION
起動時に作る AF_UNIX ソケット（reparse point）が前回のクラッシュの残骸として残ると、
Docker は「消してから作り直す」ため消せない時点でクラッシュする。残骸は通常のファイル API では
削除できず、親ディレクトリごと退避するしかない。

さらに、残骸は複数の場所（Inference manager / Secrets Engine）にできるため、
片方ずつ退避すると「その回は進むが別のソケットで落ちて新しい残骸を作る」ループから抜けられない。
このスクリプトは対象ディレクトリを同じ停止状態でまとめて退避する。

.PARAMETER Check
診断のみ行い、プロセスの停止・ディレクトリの退避・Docker の起動は一切しない。

.PARAMETER Force
docker info が正常に応答していても復旧手順を実行する。

.PARAMETER TimeoutSec
起動後に docker info の応答を待つ秒数（既定 300）。

.EXAMPLE
powershell -File recover.ps1 -Check

.EXAMPLE
powershell -File recover.ps1
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Force,
    [int]$TimeoutSec = 300
)

$ErrorActionPreference = "Stop"

# 残骸ソケットができる場所。増えたらここに足す（片方ずつ退避すると再発ループから抜けられない）
$TargetDirs = @(
    (Join-Path $env:LOCALAPPDATA "Docker\run"),
    (Join-Path $env:LOCALAPPDATA "docker-secrets-engine")
)

$ProcessPattern = '^(Docker Desktop|com\.docker\.backend|docker|docker-ai)$'
$BackendLog = Join-Path $env:LOCALAPPDATA "Docker\log\host\com.docker.backend.exe.log"

function Write-Step($msg) { Write-Host "==> $msg" }

<#
docker info はデーモンが死んでいると返らずハングし、叩くほどプロセスが溜まって状況が悪化する。
必ずジョブに逃がしてタイムアウト付きで判定する（実測）。
#>
function Test-DockerHealthy {
    param([int]$WaitSec = 12)
    $job = Start-Job -ScriptBlock { docker info 2>&1 | Out-Null; $LASTEXITCODE }
    $done = Wait-Job -Job $job -Timeout $WaitSec
    if (-not $done) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        return $false
    }
    $code = Receive-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    return ($code -eq 0)
}

function Find-DockerDesktopExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Get-LastCrashReason {
    if (-not (Test-Path -LiteralPath $BackendLog)) { return $null }
    try {
        $hits = Select-String -LiteralPath $BackendLog -Pattern "backend crashed|backend cancelling with error" -ErrorAction Stop |
                Select-Object -Last 1
        if ($hits) { return $hits.Line }
    } catch { return $null }
    return $null
}

# ---- 1. 診断 -------------------------------------------------------------
Write-Step "現状を確認します"

$healthy = Test-DockerHealthy
if ($healthy) {
    Write-Host "  docker info: 正常に応答"
} else {
    Write-Host "  docker info: 応答なし（デーモン停止 or 起動失敗）"
    $reason = Get-LastCrashReason
    if ($reason) { Write-Host "  直近のクラッシュ理由: $reason" }
}

# Docker が生きているときは、これらは「残骸」ではなく現役のソケット。表現を変える
# （正常時に「残骸候補」と出すと、無いはずの異常を疑わせて誤診を招く）
$label = "現役のソケット"
if (-not $healthy) { $label = "残骸候補" }
foreach ($d in $TargetDirs) {
    if (Test-Path -LiteralPath $d) {
        $files = @(Get-ChildItem -LiteralPath $d -Force -File -ErrorAction SilentlyContinue)
        Write-Host ("  {0}: {1} （ファイル {2} 件）" -f $label, $d, $files.Count)
    }
}

# 退避ディレクトリは 1 回の復旧につき最大 2 個（run と docker-secrets-engine）できる。
# 発生回数として数えるのは run 側だけにする（両方足すと回数が倍に見える）
$runBackups = @(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA "Docker") -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^run\.(broken|stale)-' })
$secretsBackups = @(Get-ChildItem -LiteralPath $env:LOCALAPPDATA -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match '^docker-secrets-engine\.(broken|stale)-' })
if (($runBackups.Count + $secretsBackups.Count) -gt 0) {
    Write-Host ("  過去の復旧回数: 約 {0} 回（退避ディレクトリ run {1} 個 / secrets {2} 個）" -f `
        $runBackups.Count, $runBackups.Count, $secretsBackups.Count)
}

if ($Check) {
    Write-Step "診断のみ（-Check）のため、ここで終了します"
    if ($healthy) { exit 0 }
    exit 1
}

if ($healthy -and -not $Force) {
    Write-Step "Docker は正常です。復旧手順は実行しません（強制するなら -Force）"
    exit 0
}

# ---- 2. プロセス停止 -----------------------------------------------------
Write-Step "Docker 関連プロセスを停止します"
$procs = @(Get-Process | Where-Object { $_.ProcessName -match $ProcessPattern })
if ($procs.Count -eq 0) {
    Write-Host "  停止対象なし"
} else {
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host ("  停止: {0}" -f (($procs | Select-Object -ExpandProperty ProcessName -Unique) -join ", "))
}
Start-Sleep -Seconds 6

# ---- 3. 残骸ディレクトリをまとめて退避 -----------------------------------
# 個別のソケットファイルは Remove-Item / del / \\?\ プレフィックスのいずれでも
# "The file cannot be accessed by the system." で消せない（実測）。親ごとリネームする。
Write-Step "残骸ディレクトリを退避します（削除ではなくリネーム）"
$stamp = "broken-" + (Get-Date -Format "yyyyMMddHHmm")
$failed = @()
foreach ($d in $TargetDirs) {
    if (-not (Test-Path -LiteralPath $d)) {
        Write-Host ("  なし: {0}" -f $d)
        continue
    }
    $newName = (Split-Path $d -Leaf) + "." + $stamp
    try {
        Rename-Item -LiteralPath $d -NewName $newName -ErrorAction Stop
        Write-Host ("  退避: {0} -> {1}" -f $d, $newName)
    } catch {
        Write-Host ("  失敗: {0} -> {1}" -f $d, $_.Exception.Message)
        $failed += $d
    }
}
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "退避できないディレクトリがあります。Docker を掴んでいるプロセスが残っている可能性が高いので、"
    Write-Host "サインアウト（またはOS再起動）後にもう一度実行してください。" -ForegroundColor Yellow
    exit 1
}

# ---- 4. 起動 -------------------------------------------------------------
$exe = Find-DockerDesktopExe
if (-not $exe) {
    Write-Host "Docker Desktop.exe が見つかりません。手動で起動してください。" -ForegroundColor Yellow
    exit 1
}
Write-Step "Docker Desktop を起動します"
Start-Process -FilePath $exe | Out-Null

# ---- 5. 疎通を待つ -------------------------------------------------------
Write-Step ("docker info の応答を待ちます（最大 {0} 秒）" -f $TimeoutSec)
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-DockerHealthy -WaitSec 10) {
        Write-Step "復旧しました"
        docker version --format "  Server {{.Server.Version}}"
        exit 0
    }
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "タイムアウトしました。GUI にエラーダイアログが出ていないか確認してください。" -ForegroundColor Yellow
$reason = Get-LastCrashReason
if ($reason) { Write-Host "直近のクラッシュ理由: $reason" }
Write-Host "別のソケットで落ちている場合は、そのパスを本スクリプトの `$TargetDirs に追加してから再実行してください。"
exit 1
