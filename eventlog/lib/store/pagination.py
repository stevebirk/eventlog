import pytz

from eventlog.lib.util import local_datetime_to_utc, utc_datetime_to_local


class InvalidPage(Exception):
    pass


class ByTimeRangeCursor:
    def __init__(self, event_occurred, event_id, timezone=None):
        self.occurred = local_datetime_to_utc(event_occurred, timezone)
        self.id = event_id

    def localize(self, timezone):
        self.occurred = utc_datetime_to_local(self.occurred, timezone)

    def __eq__(self, other):
        return self.occurred == other.occurred and self.id == other.id


class BySearchCursor:
    def __init__(self, page):
        self.page = page

    def localize(self, timezone):
        pass


class Page:
    def __init__(self, events, cursor, timezone=None):
        self.next = cursor
        self.events = events
        self.count = len(self.events)

        # if timezone is provided sthe result set and cursor should be
        # localized
        if timezone is not None:
            [e.localize(timezone) for e in events]

            if self.next is not None:
                self.next.localize(timezone)

    def __iter__(self):
        yield from self.events

    def __len__(self):
        return self.count
