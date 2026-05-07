$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$PyInstaller = Join-Path $RootDir ".venv\Scripts\pyinstaller.exe"
$SpecPath = Join-Path $RootDir "semanticnews.spec"
$DistAppDir = Join-Path $RootDir "dist\SemanticNews"
$DistInstanceDir = Join-Path $DistAppDir "instance"

if (-not (Test-Path $PyInstaller)) {
    Write-Error "PyInstaller не найден. Установи его командой: .\.venv\Scripts\python.exe -m pip install pyinstaller"
}

Push-Location $RootDir
try {
    # Сначала собираем one-folder desktop-приложение через заранее подготовленный spec.
    & $PyInstaller --clean --noconfirm $SpecPath

    # Runtime-файлы кладем рядом с exe, потому что frozen Config ищет instance от папки исполняемого файла.
    New-Item -ItemType Directory -Force -Path $DistInstanceDir | Out-Null

    $RuntimeFiles = @(
        @{ Source = "project\instance\app.db"; Target = "app.db" },
        @{ Source = "project\instance\news.index"; Target = "news.index" },
        @{ Source = "project\instance\news_index_ids.json"; Target = "news_index_ids.json" }
    )

    foreach ($Item in $RuntimeFiles) {
        $SourcePath = Join-Path $RootDir $Item.Source
        if (Test-Path $SourcePath) {
            Copy-Item -Force -Path $SourcePath -Destination (Join-Path $DistInstanceDir $Item.Target)
        }
    }

    $ModelSource = Join-Path $RootDir "project\instance\models\news-embeddings"
    $ModelTarget = Join-Path $DistInstanceDir "models\news-embeddings"
    if (Test-Path $ModelSource) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ModelTarget) | Out-Null
        if (Test-Path $ModelTarget) {
            Remove-Item -Recurse -Force -LiteralPath $ModelTarget
        }
        Copy-Item -Recurse -Force -Path $ModelSource -Destination $ModelTarget
    }

    # Telegram runtime содержит api_id/api_hash и личную session, поэтому по умолчанию не копируется в сборку.
    Write-Host "Telegram runtime не копируется автоматически: настрой авторизацию в собранном приложении заново."
    Write-Host "Desktop-сборка готова: $DistAppDir"
}
finally {
    Pop-Location
}
