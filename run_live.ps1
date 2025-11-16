$ErrorActionPreference = "Continue"
while ($true) {
  try {
    python .\emit_signals.py --lookback-bars 5 --touch
    python .\run_router.py
    python .\make_report.py
  } catch {
    Write-Warning $_
  }
  Start-Sleep -Seconds 300
}
