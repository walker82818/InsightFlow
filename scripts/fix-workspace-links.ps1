# fix-workspace-links.ps1
# 环境修复脚本：本机 F 盘目录 junction 无法解析（创建成功但读取失败），
# pnpm 对 workspace 包使用 junction 链接时 install 会报
#   UNKNOWN: unknown error, open '...\@insightflow\...\package.json'
# 本脚本在 pnpm install 之后运行：把 workspace 包的 junction 替换为真实复制目录。
# 注意：pnpm 每次 install 都会重建 junction，因此 install 之后需要重新运行本脚本。
param(
  [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if (-not $SkipInstall) {
  Write-Host "[1/2] pnpm install ..."
  Push-Location $root
  try {
    & pnpm install 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
      # junction 相关错误会导致非 0 退出，但依赖主体已就位，继续修复
      Write-Host "pnpm install exited with $LASTEXITCODE (junction 错误可忽略，继续修复)"
    }
  } finally {
    Pop-Location
  }
}

$pairs = @(
  @{ Link = "$root\apps\web\node_modules\@insightflow\artifact-schema"; Target = "$root\packages\artifact-schema" }
)

Write-Host "[2/2] 修复 workspace 链接（复制替代 junction）..."
foreach ($p in $pairs) {
  $link = $p.Link
  $tgt  = $p.Target
  $parent = Split-Path -Parent $link
  New-Item -ItemType Directory -Path $parent -Force | Out-Null

  if (Test-Path $link) {
    $item = Get-Item $link -Force
    if ($item.LinkType -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
      & fsutil reparsepoint delete $link 2>$null | Out-Null
    }
    # 清空旧内容（不跟随 junction）
    & robocopy "$root\scripts\_empty" $link /MIR /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
  }

  New-Item -ItemType Directory -Path $link -Force | Out-Null
  & robocopy $tgt $link /E /NFL /NDL /NJH /NJS /NC /NS /NP /XD node_modules | Out-Null
  if (Test-Path (Join-Path $link 'package.json')) {
    Write-Host "  OK  $link"
  } else {
    Write-Host "  FAIL $link"
  }
}

Write-Host "完成。之后每次 pnpm install 后需重新运行：.\scripts\fix-workspace-links.ps1 -SkipInstall"
