$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name TimeAllocator `
    time_allocator_app.py

Write-Host "Executable created at: .\dist\TimeAllocator.exe"
