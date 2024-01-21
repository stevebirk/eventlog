import unittest
import datetime
import uuid

from eventlog.lib.store.pagination import ByTimeRangeCursor


class TestPagination(unittest.TestCase):

    def test_cursor_eq(self):
        event_id_1 = uuid.uuid4()
        event_occurred_1 = datetime.datetime.utcnow()

        cursor_1 = ByTimeRangeCursor(event_occurred_1, event_id_1)
        cursor_2 = ByTimeRangeCursor(event_occurred_1, event_id_1)
        cursor_3 = ByTimeRangeCursor(event_occurred_1, uuid.uuid4())
        cursor_4 = ByTimeRangeCursor(datetime.datetime.utcnow(), event_id_1)

        self.assertTrue(cursor_1 == cursor_2)
        self.assertFalse(cursor_3 == cursor_4)
        self.assertFalse(cursor_3 == cursor_2)
        self.assertFalse(cursor_4 == cursor_1)


if __name__ == '__main__':
    unittest.main()
