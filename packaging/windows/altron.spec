# Build from repository root after: pip install -e ".[desktop,data,optimize,windows-build]"
from PyInstaller.utils.hooks import collect_all

hiddenimports, datas, binaries = [], [], []
for package in ("PySide6", "keyring", "platformdirs", "pandas", "numpy", "yaml", "MetaTrader5"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    ["src/altron/desktop/app.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["streamlit"],
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="AltronQuant",
    console=False,
    debug=False,
    upx=False,
)
