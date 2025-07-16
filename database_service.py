"""\
DatabaseService module responsible for communication with MySQL.
"""

from __future__ import annotations

from typing import Iterable, Dict, Optional
from contextlib import contextmanager
import time
import logging

logger = logging.getLogger(__name__)

try:
    import mysql.connector
except ModuleNotFoundError as exc:
    mysql = None  # type: ignore
    _IMPORT_ERROR = exc


class DatabaseConnectionError(Exception):
    """Raised when connecting to the MySQL database fails."""

    pass


class DatabaseService:
    """Сервис доступа к базе данных.

    Выполняет чтение данных из MySQL согласно предоставленной конфигурации.
    Отвечает только за операции с БД, соблюдая принцип единственной ответственности.
    """

    def __init__(self, db_config: Dict):
        """Сохраняет параметры подключения к базе данных и настраивает режим работы.

        Помимо стандартных параметров подключения допускаются специальные ключи:

        ``persistent``
            Использовать постоянное соединение вместо открытия нового при каждом запросе.

        ``pool_size``
            Размер пула соединений. При значении больше нуля используется пул.

        ``max_retries``
            Количество попыток подключения при возникновении временной ошибки.

        Raises
        ------
        DatabaseConnectionError
            Если библиотека ``mysql-connector-python`` не установлена.
        """
        self._ensure_connector()

        # Параметры управления соединениями не передаются напрямую в коннектор
        internal_keys = {"pool_size", "persistent", "max_retries"}
        self._db_config = {k: v for k, v in db_config.items() if k not in internal_keys}

        self._persistent: bool = bool(db_config.get("persistent", False))
        self._max_retries: int = int(db_config.get("max_retries", 1))

        pool_size = db_config.get("pool_size")
        self._pool: Optional[mysql.connector.pooling.MySQLConnectionPool] = None
        if pool_size:
            self._create_pool(int(pool_size))

        self._connection: Optional[mysql.connector.MySQLConnection] = None

        # Для логирования конфигурации не выводим пароль.
        safe_config = self._mask_password(db_config)
        logger.debug("DatabaseService initialized with config: %s", safe_config)

    @staticmethod
    def _mask_password(config: Dict) -> Dict:
        """Возвращает копию конфигурации с скрытым паролем."""
        redacted = dict(config)
        if "password" in redacted:
            redacted["password"] = "***"
        return redacted

    def _ensure_connector(self) -> None:
        """Проверяет наличие установленного MySQL-коннектора.

        Raises
        ------
        DatabaseConnectionError
            Если библиотека ``mysql-connector-python`` не установлена.
        """
        if mysql is None:
            raise DatabaseConnectionError(
                "Библиотека 'mysql-connector-python' не установлена"
            ) from _IMPORT_ERROR

    def _create_pool(self, size: int) -> None:
        """Создаёт пул соединений указанного размера."""
        try:
            self._pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_size=size, **self._db_config
            )
            logger.debug("MySQL connection pool created with size %s", size)
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось создать пул соединений: {exc}"
            ) from exc

    def _is_transient_error(self, exc: Exception) -> bool:
        """Определяет, относится ли ошибка подключения к временным."""
        errno = getattr(exc, "errno", None)
        transient_codes = {
            mysql.connector.errorcode.CR_SERVER_GONE_ERROR,
            mysql.connector.errorcode.CR_SERVER_LOST,
            mysql.connector.errorcode.CR_CONNECTION_ERROR,
            mysql.connector.errorcode.CR_CONN_HOST_ERROR,
        }
        return errno in transient_codes

    def _acquire_connection(self):
        """Получить соединение из пула, постоянное или новое."""
        if self._pool is not None:
            logger.debug("Acquire connection from pool")
            return self._pool.get_connection()
        if self._persistent:
            if self._connection is None or not self._connection.is_connected():
                logger.debug("Open persistent connection")
                self._connection = mysql.connector.connect(**self._db_config)
            else:
                logger.debug("Reuse persistent connection")
            return self._connection
        logger.debug("Open transient connection")
        return mysql.connector.connect(**self._db_config)

    def _release_connection(self, conn) -> None:
        """Закрыть или вернуть соединение в пул."""
        if self._pool is not None:
            logger.debug("Return connection to pool")
            conn.close()
        elif not self._persistent:
            logger.debug("Close transient connection")
            conn.close()
        else:
            logger.debug("Keep persistent connection open")

    def _get_connection_with_retry(self):
        """Подключение с учётом настроек повторов при ошибках."""
        attempts = max(1, self._max_retries)
        for attempt in range(1, attempts + 1):
            try:
                logger.debug("Opening MySQL connection (attempt %s)", attempt)
                conn = self._acquire_connection()
                logger.debug("MySQL connection opened")
                return conn
            except mysql.connector.Error as exc:
                if attempt < attempts and self._is_transient_error(exc):
                    logger.warning("Transient DB error: %s", exc)
                    time.sleep(1)
                    continue
                raise DatabaseConnectionError(
                    f"Не удалось подключиться к базе данных: {exc}"
                ) from exc

    @contextmanager
    def _connect(self):
        """Контекстный менеджер получения соединения с учётом пула и повторов."""
        self._ensure_connector()
        logger.debug("Acquire DB connection")
        conn = self._get_connection_with_retry()
        try:
            yield conn
        finally:
            logger.debug("Release DB connection")
            self._release_connection(conn)

    def check_connection(self) -> None:
        """Проверить корректность параметров подключения."""
        try:
            logger.debug("Checking database connection")
            with self._connect():
                logger.debug("Database connection successful")
        except DatabaseConnectionError:
            raise

    def get_term_labels(self, term_slugs: Iterable[str]) -> Dict[str, str]:
        """\
        Возвращает словарь ``slug -> название`` для переданных slug'ов.
        Возвращается пустой словарь, если ``term_slugs`` пуст.
        """
        if not term_slugs:
            return {}

        try:
            logger.debug("Fetching term labels: %s", term_slugs)
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    # Формируем SQL-запрос для выборки терминов
                    placeholders = ",".join(["%s"] * len(term_slugs))
                    query = (
                        "SELECT slug, name FROM wp_terms WHERE slug IN (" f"{placeholders})"
                    )
                    cursor.execute(query, list(term_slugs))

                    # Возвращаем словарь slug -> человекочитаемое имя
                    result = {slug: name for slug, name in cursor.fetchall()}
                    logger.debug("Terms fetched: %s", result)
                    return result
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось подключиться к базе данных: {exc}"
            ) from exc

    def get_products_by_skus(self, skus: Iterable[str]) -> Dict[int, Dict]:
        """\
        Получает данные товаров для указанных SKU.
        Возвращает словарь ``product_id -> данные``.
        """
        if not skus:
            return {}

        try:
            logger.debug("Fetching products for SKUs: %s", skus)
            with self._connect() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    placeholders = ",".join(["%s"] * len(skus))
                    # Загружаем вариации продуктов с указанными SKU
                    query = f"""
                        SELECT p.ID, p.post_title, p.post_parent, pm.meta_key, pm.meta_value
                        FROM wp_posts p
                        JOIN wp_postmeta pm ON p.ID = pm.post_id
                        WHERE (pm.meta_key IN ('_sku', '_price', '_regular_price', '_sale_price',
                                              '_product_attributes', '_variation_description', '_stock')
                               OR pm.meta_key LIKE 'attribute_%')
                          AND p.post_type = 'product_variation'
                          AND pm.post_id IN (
                            SELECT post_id FROM wp_postmeta WHERE meta_key = '_sku' AND meta_value IN ({placeholders})
                          )
                    """
                    cursor.execute(query, list(skus))

                    # Собираем значения мета-полей по каждой вариации
                    products: Dict[int, Dict] = {}
                    parent_ids = set()
                    for row in cursor.fetchall():
                        pid = row['ID']
                        if pid not in products:
                            products[pid] = {
                                'id': pid,
                                'parent': row['post_parent'],
                                'meta': {},
                                'title': row['post_title']
                            }
                        products[pid]['meta'][row['meta_key']] = row['meta_value']
                        parent_ids.add(row['post_parent'])

                    if parent_ids:
                        # Подгружаем родительские записи товаров
                        parent_query = (
                            "SELECT ID, post_title, post_content FROM wp_posts WHERE ID IN ("
                            f"{','.join(map(str, parent_ids))})"
                        )
                        cursor.execute(parent_query)
                        parents = {
                            row['ID']: {'title': row['post_title'], 'content': row['post_content']}
                            for row in cursor.fetchall()
                        }
                        for product in products.values():
                            parent = parents.get(product['parent'])
                            if parent:
                                product['base_title'] = parent['title']
                                product['content'] = parent['content']

                    logger.debug("Products fetched: %s", list(products.keys()))
                    return products
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось подключиться к базе данных: {exc}"
            ) from exc

