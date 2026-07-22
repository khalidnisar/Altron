from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "Install the Windows desktop application with: pip install '.[desktop,data,optimize]'"
        ) from exc

    from altron.desktop.main_window import MainWindow
    from altron.desktop.runtime import DesktopRuntime
    from altron.desktop.settings import DesktopSettings

    application = QApplication(sys.argv)
    application.setApplicationName("Altron Quant Desktop")
    application.setOrganizationName("Altron")
    settings = DesktopSettings()
    runtime = DesktopRuntime(settings.data_dir)
    window = MainWindow(settings, runtime)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
