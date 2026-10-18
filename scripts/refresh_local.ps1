<#
.SYNOPSIS
  Local refresh: market-only data fetch -> re-run the stress test -> regenerate
  README + deck -> run tests -> git add/commit/push.

.DESCRIPTION
  Run this on a normal network connection (not the dev sandbox this project was
  built in -- GDELT is abandoned as a data source for this submission, see
  docs/ASSUMPTIONS.md "Impact-score event study: not run"; this script never
  touches GDELT/Mastodon/Twitter ingestion). It only refreshes the Treasury
  curve, FRED spreads, and the two equity tickers Module B's option positions
  need (JPM, NVDA), then re-runs Module B and regenerates every number-bearing
  doc from the result.

  Each step checks its own exit code and stops the whole script immediately on
  failure -- never pushes a half-finished refresh.

.PARAMETER CommitMessage
  Optional. Defaults to a timestamped "chore: local market-data refresh" message.

.PARAMETER SkipPush
  Optional switch. Commits locally but does not push -- use this if you want to
  review `git log`/`git diff` before pushing yourself.

.EXAMPLE
  .\scripts\refresh_local.ps1
.EXAMPLE
  .\scripts\refresh_local.ps1 -CommitMessage "chore: refresh market data 2026-10-19" -SkipPush
#>
param(
    [string]$CommitMessage = "chore: local market-data refresh ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Invoke-Step {
    param([string]$Description, [string[]]$Args)
    Write-Host "`n=== $Description ===" -ForegroundColor Cyan
    & python @Args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Description (exit $LASTEXITCODE) -- stopping, nothing pushed." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Invoke-Step "1/6 Market-only data fetch (Treasury curve direct, FRED, JPM/NVDA spot)" `
    @("scripts/build_cache.py", "--market-only")

Invoke-Step "2/6 Re-run Module B stress test on existing results/signals.jsonl" `
    @("scripts/run_stress_test.py")

Invoke-Step "3/6 Regenerate README.md" `
    @("scripts/generate_readme.py")

Invoke-Step "4/6 Regenerate deck charts" `
    @("scripts/generate_deck_charts.py")

Invoke-Step "5/6 Regenerate docs/presentation.pptx" `
    @("scripts/generate_deck.py")

Invoke-Step "6/6 Run the full test suite" `
    @("-m", "pytest", "tests/", "-q")

Write-Host "`n=== Compliance audit (informational -- does not block commit/push) ===" -ForegroundColor Cyan
& python scripts/audit_compliance.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Audit reported issue(s) above (likely the still-pending docs/presentation.pdf export) -- not blocking this refresh." -ForegroundColor Yellow
}

Write-Host "`n=== git add/commit ===" -ForegroundColor Cyan
git add -A
if ($LASTEXITCODE -ne 0) { Write-Host "git add failed." -ForegroundColor Red; exit $LASTEXITCODE }

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Nothing to commit -- working tree matches HEAD after the refresh." -ForegroundColor Yellow
    exit 0
}

git commit -m $CommitMessage
if ($LASTEXITCODE -ne 0) { Write-Host "git commit failed." -ForegroundColor Red; exit $LASTEXITCODE }

if ($SkipPush) {
    Write-Host "`n-SkipPush set -- committed locally, not pushed. Run 'git push origin master' when ready." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n=== git push origin master ===" -ForegroundColor Cyan
git push origin master
if ($LASTEXITCODE -ne 0) { Write-Host "git push failed." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "`nDone -- refreshed, committed, and pushed." -ForegroundColor Green
