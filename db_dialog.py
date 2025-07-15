from PyQt5 import QtWidgets

class DBConfigDialog(QtWidgets.QDialog):
    """Dialog used for configuring MySQL connection parameters."""

    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки подключения к БД")
        self.setModal(True)

        layout = QtWidgets.QFormLayout()

        self.host_input = QtWidgets.QLineEdit(current_config.get("host", "localhost"))
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setMaximum(99999)
        self.port_input.setValue(current_config.get("port", 3306))
        self.user_input = QtWidgets.QLineEdit(current_config.get("user", ""))
        self.pass_input = QtWidgets.QLineEdit(current_config.get("password", ""))
        self.pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.db_input = QtWidgets.QLineEdit(current_config.get("database", ""))

        layout.addRow("Хост:", self.host_input)
        layout.addRow("Порт:", self.port_input)
        layout.addRow("Пользователь:", self.user_input)
        layout.addRow("Пароль:", self.pass_input)
        layout.addRow("База данных:", self.db_input)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_config(self):
        return {
            "host": self.host_input.text(),
            "port": self.port_input.value(),
            "user": self.user_input.text(),
            "password": self.pass_input.text(),
            "database": self.db_input.text()
        }