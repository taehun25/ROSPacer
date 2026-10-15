param([string]$Base = '')
$ErrorActionPreference = 'Stop'
$w2Repo = Split-Path -Parent $PSScriptRoot
$w2Base = if ($Base) { [System.IO.Path]::GetFullPath($Base) } else { Join-Path $w2Repo 'runs/w2_20261014_3rep' }
$w2Python = 'C:\Users\csilab\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$w2Script = Join-Path $PSScriptRoot 'w2_runner.py'
$w2Args = @('-u', ('"' + $w2Script + '"'), 'run', '--base', ('"' + $w2Base + '"'))
$w2PreviousUTF8 = $env:PYTHONUTF8
try {
    $env:PYTHONUTF8 = '1'
    $w2Process = Start-Process -FilePath $w2Python -ArgumentList $w2Args -WorkingDirectory $w2Repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $w2Base 'runner.stdout.log') -RedirectStandardError (Join-Path $w2Base 'runner.stderr.log') -PassThru
    $w2Launch = [ordered]@{ pid=$w2Process.Id; started_UTC=[DateTime]::UtcNow.ToString('o'); independent_of_codex=$true; script=$w2Script; base=$w2Base; repeats=3; additional_repeats='review results before scheduling'; }
    $w2Launch | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $w2Base 'launch.json') -Encoding utf8
    $w2Launch | ConvertTo-Json
} finally {
    $env:PYTHONUTF8 = $w2PreviousUTF8
}
