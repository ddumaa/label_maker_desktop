from PyQt5 import QtWidgets, QtGui, QtCore
import sys
import os
import json
import tempfile

from logging_setup import configure_logging

configure_logging()

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ModuleNotFoundError as exc:  # Коннектор MySQL не установлен
    mysql = None  # type: ignore
    MYSQL_AVAILABLE = False
    MYSQL_IMPORT_ERROR = exc
from config_loader import load_settings, load_db_config

from preview_engine import generate_preview_pdf, convert_pdf_to_image
from label_engine import generate_labels_entry
from database_service import DatabaseConnectionError, DatabaseService
from db_dialog import DBConfigDialog
from label_settings import LabelSettingsDialog

class LabelMakerApp(QtWidgets.QMainWindow):
    """Main application window for the label maker GUI."""

    def __init__(self):
        super().__init__()
        # Минимальная инициализация: загружаем конфигурацию и строим интерфейс
        self.settings: dict = {}
        self.db_config: dict = {}
        self._db_loaded = False

        self._load_config()
        self._build_ui()
        if self._db_loaded:
            self.update_db_status()

        # Последующая инициализация выполняется в отдельных методах

    def _load_config(self) -> None:
        """Загружает настройки приложения и параметры подключения к БД."""

        # Загружаем настройки генерации этикеток
        try:
            self.settings = load_settings()
        except FileNotFoundError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не найден файл настроек:\n{exc}"
            )
            # При ошибке применяем настройки по умолчанию
            self.settings = {}

        self._db_loaded = True
        try:
            self.db_config = load_db_config()
        except FileNotFoundError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не найден файл конфигурации БД:\n{exc}"
            )
            self.db_config = {}
            self._db_loaded = False
        except Exception as exc:
            # mysql.connector.Error может быть недоступен при отсутствии
            # зависимости, поэтому перехватываем общее исключение.
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка при загрузке конфигурации БД:\n{exc}"
            )
            self.db_config = {}
            self._db_loaded = False

    def _build_ui(self) -> None:
        """Создаёт элементы интерфейса и привязывает обработчики событий."""

        self.setWindowTitle("Label Maker")
        self.setGeometry(100, 100, 1000, 600)

        # Главные контейнеры
        main_layout = QtWidgets.QHBoxLayout()
        left_layout = QtWidgets.QVBoxLayout()
        right_layout = QtWidgets.QVBoxLayout()

        # Список SKU
        self.sku_list = QtWidgets.QListWidget()
        self.sku_list.itemClicked.connect(self.preview_selected_sku)
        left_layout.addWidget(QtWidgets.QLabel("📦 Артикулы"))
        left_layout.addWidget(self.sku_list)

        # Статус БД и кнопка проверки
        self.db_status_label = QtWidgets.QLabel()
        self.test_conn_button = QtWidgets.QPushButton("Тест подключения")
        self.test_conn_button.clicked.connect(self.test_db_connection)

        db_status_layout = QtWidgets.QHBoxLayout()
        db_status_layout.addWidget(self.db_status_label)
        db_status_layout.addWidget(self.test_conn_button)
        left_layout.addLayout(db_status_layout)

        self.load_button = QtWidgets.QPushButton("📁 Загрузить SKU")
        self.load_button.clicked.connect(self.load_sku_file)
        left_layout.addWidget(self.load_button)

        self.db_settings_btn = QtWidgets.QPushButton("⚙ Настройки БД")
        self.db_settings_btn.clicked.connect(self.show_db_config_dialog)
        left_layout.addWidget(self.db_settings_btn)

        self.label_settings_btn = QtWidgets.QPushButton("🏷️ Настройки этикетки")
        self.label_settings_btn.clicked.connect(self.show_label_settings_dialog)
        left_layout.addWidget(self.label_settings_btn)

        self.generate_button = QtWidgets.QPushButton("📤 Сгенерировать PDF")
        self.generate_button.clicked.connect(self.generate_pdf)
        left_layout.addWidget(self.generate_button)

        self.preview_mode = QtWidgets.QComboBox()
        self.preview_mode.addItems(["👁 Одна этикетка", "🗒️ Полный лист"])
        self.preview_mode.currentIndexChanged.connect(self.update_preview)
        left_layout.addWidget(self.preview_mode)

        self.log_output = QtWidgets.QTextEdit()
        self.log_output.setReadOnly(True)
        left_layout.addWidget(QtWidgets.QLabel("📝 Лог"))
        left_layout.addWidget(self.log_output)

        # Область превью
        self.image_label = QtWidgets.QLabel("Превью")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        right_layout.addWidget(self.image_label)

        main_widget = QtWidgets.QWidget()
        main_layout.addLayout(left_layout, 3)
        main_layout.addLayout(right_layout, 5)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def load_sku_file(self):
        """Загружает текстовый файл со SKU и заполняет список.

        Parameters
        ----------
        self : LabelMakerApp
            Экземпляр главного окна.

        Side effects
        ------------
        Открывает диалог выбора файла, заполняет ``sku_list`` и
        добавляет запись в ``log_output``.
        """
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл SKU", "", "Text Files (*.txt)")
        if filepath:
            with open(filepath, "r", encoding="utf-8") as f:
                skus = [line.strip() for line in f if line.strip()]
                self.sku_list.clear()
                self.sku_list.addItems(skus)
            self.log_output.append(f"✅ Загружено SKU: {len(skus)}")

    def preview_selected_sku(self):
        """Отрисовывает превью для выбранного SKU в текущем режиме.

        Parameters
        ----------
        self : LabelMakerApp

        Side effects
        ------------
        Вызывает отображение одной этикетки или целого листа и пишет
        сообщение в ``log_output``.
        """
        sku = self.sku_list.currentItem().text()
        mode = self.preview_mode.currentIndex()
        if mode == 0:
            self.log_output.append(f"👁 Превью одной этикетки: {sku}")
            self.show_label_preview(sku)
        else:
            self.log_output.append(f"📄 Превью целого листа: {sku}")
            self.show_page_preview(sku)

    def update_preview(self):
        """Обновляет превью выбранного SKU при смене режима.

        Side effects
        ------------
        При наличии выбранного элемента вызывает ``preview_selected_sku``.
        """
        if self.sku_list.currentItem():
            self.preview_selected_sku()

    def show_label_preview(self, sku):
        """Preview a single label for ``sku``."""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                pdf_path = tmp_pdf.name

            generate_preview_pdf(pdf_path, sku, self.settings, self.db_config, generate_labels_entry)
            image = convert_pdf_to_image(pdf_path)
            if image:
                image_qt = QtGui.QImage(image.tobytes("raw", "RGB"), image.width, image.height, QtGui.QImage.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(image_qt)
                self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), QtCore.Qt.KeepAspectRatio))
        except DatabaseConnectionError as exc:
            QtWidgets.QMessageBox.critical(self, "Ошибка БД", str(exc))
        except Exception as e:
            self.log_output.append(f"❌ Ошибка при превью: {e}")

    def show_page_preview(self, sku):
        """Preview a full page filled with the same SKU."""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                pdf_path = tmp_pdf.name

            count = self.settings.get("labels_per_page", 3)
            generate_preview_pdf(pdf_path, [sku] * count, self.settings, self.db_config, generate_labels_entry)
            image = convert_pdf_to_image(pdf_path)
            if image:
                image_qt = QtGui.QImage(image.tobytes("raw", "RGB"), image.width, image.height, QtGui.QImage.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(image_qt)
                self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), QtCore.Qt.KeepAspectRatio))
        except DatabaseConnectionError as exc:
            QtWidgets.QMessageBox.critical(self, "Ошибка БД", str(exc))
        except Exception as e:
            self.log_output.append(f"❌ Ошибка при превью: {e}")

    def generate_pdf(self):
        """Генерирует итоговый PDF по всем SKU из списка.

        Parameters
        ----------
        self : LabelMakerApp

        Side effects
        ------------
        Создаёт файл PDF, выводит уведомления и на Windows открывает
        сгенерированный файл.
        """
        skus = [self.sku_list.item(i).text() for i in range(self.sku_list.count())]
        if not skus:
            QtWidgets.QMessageBox.warning(self, "Внимание", "Список артикулов пуст.")
            return

        try:
            generate_labels_entry(skus, self.settings, self.db_config)
            self.log_output.append(f"✅ PDF сгенерирован: {self.settings['output_file']}")
            QtWidgets.QMessageBox.information(self, "Готово", f"PDF сгенерирован:\n{self.settings['output_file']}")

            if sys.platform == "win32":
                os.startfile(self.settings['output_file'])

        except DatabaseConnectionError as exc:
            QtWidgets.QMessageBox.critical(self, "Ошибка БД", str(exc))
        except Exception as e:
            self.log_output.append(f"❌ Ошибка генерации: {e}")
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сгенерировать PDF:\n{str(e)}")

    def show_db_config_dialog(self):
        """Отображает диалог настроек БД и сохраняет результат.

        Parameters
        ----------
        self : LabelMakerApp

        Side effects
        ------------
        Сохраняет конфигурацию в файл, обновляет статус подключения и
        пишет сообщение в ``log_output``.
        """
        dialog = DBConfigDialog(self, self.db_config)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.db_config = dialog.get_config()
            with open("db_config.json", "w", encoding="utf-8") as f:
                json.dump(self.db_config, f, indent=2)
            self.log_output.append("💾 Настройки БД обновлены")
            self.update_db_status()

    def show_label_settings_dialog(self):
        """Открывает диалог настроек этикетки и применяет изменения.

        Parameters
        ----------
        self : LabelMakerApp

        Side effects
        ------------
        Сохраняет новые параметры в файл и добавляет запись в лог.
        """
        dialog = LabelSettingsDialog(self, self.settings)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.settings = dialog.get_settings()
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            self.log_output.append("💾 Настройки этикетки обновлены")

    def update_db_status(self) -> bool:
        """Обновляет индикатор подключения к базе данных.

        Возвращает ``True`` при успешном соединении, иначе ``False``.
        Метод реализует отдельную ответственность — проверку состояния БД
        и обновление визуального статуса.
        """
        try:
            service = DatabaseService(self.db_config)
            service.check_connection()
            self.db_status_label.setText("🟢 Подключено к БД")
            self.db_status_label.setStyleSheet("color: green;")
            return True
        except DatabaseConnectionError:
            self.db_status_label.setText("🔴 Нет подключения к БД")
            self.db_status_label.setStyleSheet("color: red;")
            return False
        except Exception:
            self.db_status_label.setText("🔴 Нет подключения к БД")
            self.db_status_label.setStyleSheet("color: red;")
            return False

    def test_db_connection(self) -> None:
        """Тестирует соединение с базой данных и сообщает результат.

        Метод предназначен для ручного запуска пользователем. Сначала
        обновляется индикатор состояния, затем результат отображается в
        текстовом логе приложения.
        """

        # Сначала обновляем индикатор состояния, затем логируем итог
        is_connected = self.update_db_status()
        if is_connected:
            self.log_output.append("✅ Соединение с БД успешно")
        else:
            self.log_output.append("❌ Не удалось подключиться к БД")


def run_gui():
    """Entry point to launch the graphical interface."""
    app = QtWidgets.QApplication(sys.argv)

    if not MYSQL_AVAILABLE:
        # Показываем пользователю инструкцию по установке отсутствующей зависимости
        QtWidgets.QMessageBox.critical(
            None,
            "Отсутствует зависимость",
            (
                "Модуль 'mysql-connector-python' не установлен.\n"
                "Установите его командой:\n"
                "    pip install mysql-connector-python"
            ),
        )
        sys.exit(1)

    window = LabelMakerApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()
