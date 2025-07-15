from PyQt5 import QtWidgets, QtGui, QtCore
import sys
import os
import json
import tempfile
import mysql.connector
from config_loader import load_settings, load_db_config

from preview_engine import generate_preview_pdf, convert_pdf_to_image
from label_engine import generate_labels_entry
from db_dialog import DBConfigDialog
from label_settings import LabelSettingsDialog

class LabelMakerApp(QtWidgets.QMainWindow):
    """Main application window for the label maker GUI."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Label Maker")
        self.setGeometry(100, 100, 1000, 600)

        # Load application configuration with error handling
        # Загрузка настроек и параметров БД может завершиться ошибкой,
        # поэтому оборачиваем вызовы в try/except и отображаем диалог с ошибкой.
        try:
            self.settings = load_settings()
        except FileNotFoundError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не найден файл настроек:\n{exc}"
            )
            # При ошибке продолжаем работу с пустыми настройками
            self.settings = {}

        # Флаг, успешно ли загружена конфигурация БД
        db_loaded = True
        try:
            self.db_config = load_db_config()
        except FileNotFoundError as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не найден файл конфигурации БД:\n{exc}"
            )
            self.db_config = {}
            db_loaded = False
        except mysql.connector.Error as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка MySQL при загрузке конфигурации:\n{exc}"
            )
            self.db_config = {}
            db_loaded = False

        # UI
        main_layout = QtWidgets.QHBoxLayout()
        left_layout = QtWidgets.QVBoxLayout()
        right_layout = QtWidgets.QVBoxLayout()

        self.sku_list = QtWidgets.QListWidget()
        self.sku_list.itemClicked.connect(self.preview_selected_sku)
        left_layout.addWidget(QtWidgets.QLabel("📦 Артикулы"))
        left_layout.addWidget(self.sku_list)
        
        self.db_status_label = QtWidgets.QLabel()
        left_layout.addWidget(self.db_status_label)
        # Проверяем подключение к БД только если конфигурация загружена
        if db_loaded:
            self.update_db_status()

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

    def update_db_status(self):
        """Проверяет подключение к БД и обновляет индикатор в интерфейсе.

        Parameters
        ----------
        self : LabelMakerApp

        Side effects
        ------------
        Изменяет текст и цвет метки ``db_status_label`` в зависимости
        от результата попытки подключения.
        """
        try:
            import mysql.connector
            conn = mysql.connector.connect(**self.db_config)
            conn.close()
            self.db_status_label.setText("🟢 Подключено к БД")
            self.db_status_label.setStyleSheet("color: green;")
        except Exception as e:
            self.db_status_label.setText("🔴 Нет подключения к БД")
            self.db_status_label.setStyleSheet("color: red;")


def run_gui():
    """Entry point to launch the graphical interface."""
    app = QtWidgets.QApplication(sys.argv)
    window = LabelMakerApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()
