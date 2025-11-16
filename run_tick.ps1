$py = 'C:\XY\venv\Scripts\python.exe'
Push-Location 'C:\XY'
& $py '.\emit_signals.py' --lookback-bars 5 --touch
& $py '.\run_router.py'
Pop-Location
