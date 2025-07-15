"""\
DatabaseService module responsible for communication with MySQL.
"""

from __future__ import annotations

from typing import Iterable, Dict
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
        """Сохраняет параметры подключения к базе данных.

        При инициализации конфигурация выводится в лог с маскированием
        пароля, чтобы избежать утечки чувствительных данных.

        Raises
        ------
        DatabaseConnectionError
            Если библиотека ``mysql-connector-python`` не установлена.
        """
        self._ensure_connector()
        self._db_config = db_config

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

    def _connect(self):
        """Return a MySQL connection using stored configuration.

        Raises
        ------
        DatabaseConnectionError
            Если не удаётся подключиться к БД.
        """
        self._ensure_connector()
        try:
            logger.debug("Opening MySQL connection")
            conn = mysql.connector.connect(**self._db_config)
            logger.debug("MySQL connection established")
            return conn
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось подключиться к базе данных: {exc}"
            ) from exc

    def check_connection(self) -> None:
        """Проверить корректность параметров подключения."""
        self._ensure_connector()

        try:
            logger.debug("Checking database connection")
            with mysql.connector.connect(**self._db_config):
                logger.debug("Database connection successful")
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось подключиться к базе данных: {exc}"
            ) from exc

    def get_term_labels(self, term_slugs: Iterable[str]) -> Dict[str, str]:
        """\
        Возвращает словарь ``slug -> название`` для переданных slug'ов.
        Возвращается пустой словарь, если ``term_slugs`` пуст.
        """
        self._ensure_connector()

        if not term_slugs:
            return {}

        try:
            logger.debug("Fetching term labels: %s", term_slugs)
            with mysql.connector.connect(**self._db_config) as conn:
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
        self._ensure_connector()

        if not skus:
            return {}

        try:
            logger.debug("Fetching products for SKUs: %s", skus)
            with mysql.connector.connect(**self._db_config) as conn:
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

