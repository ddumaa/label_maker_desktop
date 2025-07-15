"""\
DatabaseService module responsible for communication with MySQL.
"""

from __future__ import annotations

from typing import Iterable, Dict
import mysql.connector


class DatabaseConnectionError(Exception):
    """Raised when connecting to the MySQL database fails."""

    pass


class DatabaseService:
    """Сервис доступа к базе данных.

    Выполняет чтение данных из MySQL согласно предоставленной конфигурации.
    Отвечает только за операции с БД, соблюдая принцип единственной ответственности.
    """

    def __init__(self, db_config: Dict):
        """Сохраняет параметры подключения к базе данных."""
        self._db_config = db_config

    def _connect(self):
        """Return a MySQL connection using stored configuration.

        Raises
        ------
        DatabaseConnectionError
            Если не удаётся подключиться к БД.
        """
        try:
            return mysql.connector.connect(**self._db_config)
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(
                f"Не удалось подключиться к базе данных: {exc}"
            ) from exc

    def check_connection(self) -> None:
        """Verify that connection parameters are valid by opening a connection.

        The method immediately closes the connection after opening it.  Any
        errors raised during connection are rethrown as
        :class:`DatabaseConnectionError`.
        """
        conn = self._connect()
        conn.close()

    def get_term_labels(self, term_slugs: Iterable[str]) -> Dict[str, str]:
        """\
        Возвращает словарь ``slug -> название`` для переданных slug'ов.
        Возвращается пустой словарь, если ``term_slugs`` пуст.
        """
        if not term_slugs:
            return {}

        conn = self._connect()
        cursor = conn.cursor()

        placeholders = ",".join(["%s"] * len(term_slugs))
        query = f"SELECT slug, name FROM wp_terms WHERE slug IN ({placeholders})"
        cursor.execute(query, list(term_slugs))

        result = {slug: name for slug, name in cursor.fetchall()}

        cursor.close()
        conn.close()
        return result

    def get_products_by_skus(self, skus: Iterable[str]) -> Dict[int, Dict]:
        """\
        Получает данные товаров для указанных SKU.
        Возвращает словарь ``product_id -> данные``.
        """
        if not skus:
            return {}

        conn = self._connect()
        cursor = conn.cursor(dictionary=True)

        placeholders = ",".join(["%s"] * len(skus))
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
            parent_query = f"SELECT ID, post_title, post_content FROM wp_posts WHERE ID IN ({','.join(map(str, parent_ids))})"
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

        cursor.close()
        conn.close()
        return products

