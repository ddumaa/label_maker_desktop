import unittest
from unittest.mock import MagicMock, patch
import mysql.connector

from database_service import DatabaseService, DatabaseConnectionError


class DatabaseServiceContextManagerTests(unittest.TestCase):
    """Тесты корректного закрытия соединений и курсоров."""

    def setUp(self):
        self.service = DatabaseService({'host': 'localhost'})

    def _mock_connection(self, fail_execute=False):
        """Создаёт мок соединения и курсора."""
        cursor = MagicMock()
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        cursor_manager.__exit__.return_value = None
        if fail_execute:
            cursor.execute.side_effect = mysql.connector.Error('boom')
        else:
            cursor.fetchall.return_value = [('a', 'A')]
        conn = MagicMock()
        conn.cursor.return_value = cursor_manager
        conn.is_connected.return_value = True
        return conn, cursor_manager

    def test_get_term_labels_closes_resources_on_success(self):
        conn, cursor_manager = self._mock_connection()
        with patch('mysql.connector.connect', return_value=conn):
            result = self.service.get_term_labels(['a'])
        self.assertEqual(result, {'a': 'A'})
        conn.close.assert_called_once()
        cursor_manager.__exit__.assert_called_once()

    def test_get_term_labels_closes_resources_on_error(self):
        conn, cursor_manager = self._mock_connection(fail_execute=True)
        with patch('mysql.connector.connect', return_value=conn):
            with self.assertRaises(DatabaseConnectionError):
                self.service.get_term_labels(['a'])
        conn.close.assert_called_once()
        cursor_manager.__exit__.assert_called_once()

    def test_connection_error_raises_custom_exception(self):
        with patch('mysql.connector.connect', side_effect=mysql.connector.Error('fail')):
            with self.assertRaises(DatabaseConnectionError):
                self.service.check_connection()


class DatabaseServiceRetryTests(unittest.TestCase):
    """Тесты повторного подключения при временных ошибках."""

    def test_retry_on_transient_error(self):
        service = DatabaseService({'host': 'localhost', 'max_retries': 2})
        conn = MagicMock()
        transient = mysql.connector.Error('boom')
        transient.errno = mysql.connector.errorcode.CR_SERVER_LOST
        with patch('mysql.connector.connect', side_effect=[transient, conn]) as mock_connect:
            with service._connect():
                pass
        self.assertEqual(mock_connect.call_count, 2)
        conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
