from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True, timeout=300)


def main() -> int:
    if platform.system() != "Windows":
        print("O smoke test do executavel e exclusivo do Windows.")
        return 0

    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    (ROOT / "DJEN Monitor.spec").unlink(missing_ok=True)

    run(
        sys.executable, "-m", "PyInstaller", "--clean", "--onefile", "--noconsole",
        "--name", "DJEN Monitor", "--version-file", "windows/version_info.txt",
        "--collect-all", "openpyxl", "--collect-all", "tzdata", "--collect-all", "certifi",
        "launcher.py",
    )
    exe = DIST / "DJEN Monitor.exe"
    if not exe.exists() or exe.stat().st_size == 0:
        raise RuntimeError("PyInstaller nao produziu DJEN Monitor.exe")
    run(str(exe), "--self-test")
    run(str(exe), "--self-test-stable-copy")
    run(str(exe), "--self-test-console")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
