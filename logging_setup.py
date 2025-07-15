"""Настройка логирования приложения."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def configure_logging(log_file: str = "app.log") -> None:
    """Настроить глобальный логгер приложения.

    Создаёт ``RotatingFileHandler`` объёмом до 1 МБ с тремя резервными
    файлами и задаёт формат сообщений вида
    ``'%(asctime)s [%(levelname)s] %(name)s: %(message)s'``.
    Корневому логгеру присваивается уровень ``DEBUG``. Дополнительно
    устанавливается ``StreamHandler`` для вывода сообщений в консоль.

    Parameters
    ----------
    log_file : str
        Путь к файлу, в который будут сохраняться логи.
    """
    # Получаем корневой логгер и задаём ему уровень
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Формат вывода для всех обработчиков
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # FileHandler с ротацией для сохранения истории логов
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # И дополнительно выводим сообщения в консоль
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

