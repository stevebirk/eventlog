import logging

from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras
import psycopg2.extensions

_LOG = logging.getLogger(__name__)

_MIN_RETRIES = 5


psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)


class Pool:
    def __init__(self, min_conn, max_conn, database, user, password):

        self.database = database
        self.user = user
        self.password = password
        self.min_conn = min_conn
        self.max_conn = max_conn

        self._impl = psycopg2.pool.ThreadedConnectionPool(
            min_conn,
            max_conn,
            database=database,
            user=user,
            password=password
        )

    @contextmanager
    def connect(self, dry=True, error_message="", dict_cursor=False):

        conn = None

        cursor = None
        cursor_factory = None

        if dict_cursor:
            cursor_factory = psycopg2.extras.RealDictCursor

        # cap the retry attempts to the number of connections being kept by
        # the pool
        retries = self.min_conn or _MIN_RETRIES

        while conn is None:
            try:
                conn = self._impl.getconn()

                # this is the default, but here incase that changes
                conn.autocommit = False

                # cause round trip to db to confirm connectivity
                conn.isolation_level

            except psycopg2.OperationalError as oe:

                if not retries or conn is None:
                    _LOG.exception('unable to connect to "%s"', self.database)
                    raise

                retries -= 1

                # this is here because passing close=True to putconn doesn't
                # work as expected
                conn.close()

                self._impl.putconn(conn)

                conn = None

        try:
            with conn.cursor(cursor_factory=cursor_factory) as cur:
                yield cur

            if not dry:
                conn.commit()
            else:
                conn.rollback()

        except Exception as e:

            if not conn.closed:
                conn.rollback()

            if error_message:
                _LOG.exception(error_message)

            raise
        finally:
            self._impl.putconn(conn)
