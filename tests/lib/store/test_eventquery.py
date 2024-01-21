import unittest

from eventlog.lib.store.eventquery import EventQuery
from eventlog.lib.store.query import Query


class TestEventQuery(unittest.TestCase):

    def test_add_first_clause(self):
        eq = EventQuery(
            Query("select {events}.* from events {events}"),
            embed_feeds=False,
            embed_related=False
        )

        eq.add_clause("{events}.is_related=%s", (False,))

        self.assertIn("where e.is_related", eq.query)


if __name__ == '__main__':
    unittest.main()
