#!/usr/bin/env python3
"""\
Скрипт установки зависимостей проекта.

Читает список пакетов из ``requirements.txt``,
определяет отсутствующие и устанавливает их через ``pip``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

import pkg_resources


class RequirementsReader:
    """Читает файл ``requirements.txt`` и возвращает имена пакетов."""

    def __init__(self, file_path: str = "requirements.txt") -> None:
        self._file_path = Path(file_path)

    def read(self) -> List[str]:
        """Возвращает список пакетов из файла."""
        if not self._file_path.exists():
            raise FileNotFoundError(f"Файл {self._file_path} не найден")
        with self._file_path.open("r", encoding="utf-8") as fh:
            return [
                line.strip()
                for line in fh
                if line.strip() and not line.startswith("#")
            ]


class PackageVerifier:
    """Проверяет наличие установленных пакетов."""

    def __init__(self, packages: Iterable[str]) -> None:
        self._packages = list(packages)

    def get_missing(self) -> List[str]:
        """Возвращает список отсутствующих пакетов."""
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = [
            pkg
            for pkg in self._packages
            if pkg_resources.safe_name(pkg).lower() not in installed
        ]
        return missing


class PackageInstaller:
    """Отвечает за установку пакетов через ``pip``."""

    def __init__(self, python_executable: str = sys.executable) -> None:
        # Команда запуска ``pip`` через текущий интерпретатор
        self._pip_cmd = [python_executable, "-m", "pip", "install"]

    def install(self, packages: Iterable[str]) -> None:
        """Запускает процесс установки перечисленных пакетов."""
        pkgs = list(packages)
        if not pkgs:
            return
        cmd = self._pip_cmd + pkgs
        subprocess.check_call(cmd)


def main() -> None:
    """Точка входа скрипта."""
    reader = RequirementsReader()
    required = reader.read()

    verifier = PackageVerifier(required)
    missing = verifier.get_missing()

    if not missing:
        print("Все зависимости уже установлены.")
        return

    print("Устанавливаются недостающие пакеты: ", ", ".join(missing))
    installer = PackageInstaller()
    try:
        installer.install(missing)
    except subprocess.CalledProcessError as exc:
        print(f"Ошибка при установке пакетов: {exc}")
        sys.exit(exc.returncode)
    print("Установка зависимостей завершена.")


if __name__ == "__main__":
    main()
