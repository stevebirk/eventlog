import unittest
import unittest.mock

import gevent
import gevent.event
import gevent.monkey
gevent.monkey.patch_all()

# psycopg2 monkey patch!
import psycogreen.gevent  # noqa: E402
psycogreen.gevent.patch_psycopg()

import psycopg2  # noqa: E402

from eventlog.lib.store.pool import Pool  # noqa: E402


def patch_pool(p, num_bad_conn=None, num_good_conn=0):

    if num_bad_conn is None:
        num_bad_conn = p.min_conn

    bad_conn = unittest.mock.Mock()

    type(bad_conn).isolation_level = unittest.mock.PropertyMock(
        side_effect=psycopg2.OperationalError
    )

    side_effect = [bad_conn] * num_bad_conn

    if num_good_conn:
        side_effect += [p._impl.getconn() for i in range(num_good_conn)]

    mock_pool = unittest.mock.Mock()

    mock_pool.getconn.side_effect = side_effect

    p._impl = mock_pool

    return mock_pool


class TestPool(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.database = "test"
        cls.user = "test"
        cls.password = "test"

    def test_reconnect_retries_exceeded(self):
        min_conn = 5
        max_conn = 10

        p = Pool(min_conn, max_conn, self.database, self.user, self.password)

        patch_pool(p, num_bad_conn=min_conn + 1)

        with self.assertRaises(psycopg2.OperationalError):
            with p.connect() as cur:
                cur.execute("select 1")

    def test_reconnect(self):

        min_conn = 10
        max_conn = 20

        p = Pool(min_conn, max_conn, self.database, self.user, self.password)

        def work(e):
            with p.connect() as cur:

                e.wait()

                cur.execute("select 1")

                res = cur.fetchall()[0][0]

                self.assertEqual(res, 1, "bad select result")

        def make_queries():
            e = gevent.event.Event()

            g = []

            for i in range(max_conn):
                g.append(gevent.spawn(work, e))

            e.set()

            gevent.joinall(g)

        # initial use of pool
        make_queries()

        # simulate disconnections
        mock_pool = patch_pool(
            p,
            num_bad_conn=min_conn,
            num_good_conn=max_conn
        )

        # no queries should fail
        make_queries()

        self.assertEqual(mock_pool.getconn.call_count, min_conn + max_conn)


if __name__ == '__main__':
    unittest.main()
