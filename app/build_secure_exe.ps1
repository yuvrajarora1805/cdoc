Write-Host "============================================="
Write-Host "Building Secure Professional EXE for HelixCare"
Write-Host "============================================="

# 1. Compile Python to C Extensions using Cython
Write-Host "`n[1/3] Securing source code with Cython..."
python setup_cython.py build_ext --inplace
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Cython compilation failed. Ensure you have Microsoft Visual C++ Build Tools installed." -ForegroundColor Red
    exit 1
}

# Clean up the generated .c file to keep things tidy
if (Test-Path "run_carm_viewer.c") {
    Remove-Item "run_carm_viewer.c"
}

# 2. Package with PyInstaller
Write-Host "`n[2/3] Packaging application with PyInstaller..."
# Ensure the icon exists, else it will fail
if (-not (Test-Path "icon.ico")) {
    Write-Host "Warning: icon.ico not found! Please place an icon.ico file in the app directory." -ForegroundColor Yellow
    Write-Host "The build might fail if PyInstaller expects it." -ForegroundColor Yellow
}

pyinstaller --clean HelixCare.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: PyInstaller packaging failed." -ForegroundColor Red
    exit 1
}

# 3. Create Setup Installer using Inno Setup
Write-Host "`n[3/3] Creating Setup Wizard with Inno Setup..."
$innoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (Test-Path $innoCompiler) {
    & $innoCompiler "installer.iss"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nSuccess! The installer has been created in app\installer\HelixCare_Setup.exe" -ForegroundColor Green
    } else {
        Write-Host "Error: Inno Setup compilation failed." -ForegroundColor Red
    }
} else {
    Write-Host "`nInno Setup Compiler (ISCC.exe) not found at default location." -ForegroundColor Yellow
    Write-Host "Please install Inno Setup 6, or open 'installer.iss' manually in Inno Setup to compile the setup wizard." -ForegroundColor Yellow
}

Write-Host "============================================="
Write-Host "Build Process Complete."
Write-Host "============================================="
