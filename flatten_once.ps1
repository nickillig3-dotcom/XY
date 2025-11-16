$ErrorActionPreference = "Stop"

# Immer ins Skriptverzeichnis (wichtig für Scheduled Task)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
try {
  # CSV sicherstellen
  $csv = Join-Path $here 'results\live\signals.csv'
  if (-not (Test-Path $csv)) {
    'time,symbol,timeframe,action,price,stop_px,strategy_key' | Set-Content -Encoding UTF8 $csv
  }

  # Kill-Switch setzen: blockt neue Entries, Close bleibt erlaubt
  $kill = Join-Path $here 'results\live\KILL'
  New-Item -ItemType File $kill -Force | Out-Null

  # State laden
  $statePath = Join-Path $here 'results\live\state.json'
  if (-not (Test-Path $statePath)) { throw "state.json not found: $statePath" }
  $st  = Get-Content $statePath -Raw | ConvertFrom-Json
  $now = (Get-Date).ToUniversalTime().ToString('s') + 'Z'

  # Für jede offene Position Flip-Signal (Preis=Entry; Stop=Entry±sl) erzeugen
  foreach ($prop in $st.positions.PSObject.Properties) {
    $key = $prop.Name; $pos = $prop.Value
    $sym = ($key -split '\|')[0]
    $tf  = ($key -split '\|')[-1]
    $sl  = [double](($key -split '\|sl')[1] -split '\|')[0]   # z.B. 0.0100
    $px  = [double]$pos.entry_px

    if ($pos.side -eq 1) { $act='entry_short'; $stop=[math]::Round($px*(1+$sl),6) }
    else                  { $act='entry_long' ; $stop=[math]::Round($px*(1-$sl),6) }

    "$now,$sym,$tf,$act,$px,$stop,$key" | Add-Content -Encoding UTF8 $csv
  }

  # Router mit venv-Python ausführen
  $py = Join-Path $here 'venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { $py = 'python' }  # Fallback
  & $py '.\run_router.py'

  # Kontrolle
  $st2 = Get-Content $statePath -Raw | ConvertFrom-Json
  "Open positions after FLAT: $($st2.positions.PSObject.Properties.Count)"
}
finally {
  # Kill-Switch wieder entfernen
  Remove-Item $kill -ErrorAction SilentlyContinue
  Pop-Location
}
