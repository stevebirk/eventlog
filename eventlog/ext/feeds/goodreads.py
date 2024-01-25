import datetime
import enum
import pytz

import xmltodict

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event


class Shelves(enum.Enum):
    CURRENTLY_READING = 0
    READ = 1

    def __str__(self):
        return self.name.lower().replace('_', '-')


class InvalidShelvesState(Exception):
    pass


class Goodreads(Feed):
    """
    This feed uses Goodreads RSS feeds to track reading activity. It assumes
    the following flow:

    1. user moves book to currently-reading shelf (i.e. by marking as currently
       reading)
    2. user moves book to read shelf (by updating reading progress to complete)

    This feed assumes at most one book is in this flow at a time. If more than
    one book exists as currently reading, it will fail. To simulate DNF remove
    the book from currently reading, but do not move it to read.

    Books can be added to the to-read shelf at any point without any effect on
    this feed.

    The feed will produce 2 events:
    1. when user starts reading a book
    2. when user completes a book
    """

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.shelves = []
        self.shelf = None

    def create_url(self):
        if self.shelf is None:
            return None

        return "https://www.goodreads.com/review/list_rss/%d?shelf=%s" % (
            self.config['user_id'],
            self.shelf
        )

    def parse_date(self, s):
        dt = datetime.datetime.strptime(
            s,
            '%a, %d %b %Y %H:%M:%S %z'  # i.e. Fri, 29 Dec 2023 15:21:59 -0800
        )

        utc_dt = pytz.utc.normalize(
            dt.astimezone(pytz.utc)
        )

        return utc_dt.replace(tzinfo=None)

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.link = "https://www.goodreads.com/book/show/%s" % (raw["book_id"])
        e.title = raw["title"]
        e.text = str(self.shelf)
        e.occurred = self.parse_date(raw["user_date_added"])
        e.raw = raw
        e.original_url = raw['book_large_image_url']

        return e

    def init_parse_params(self, **kwargs):
        self.shelves = [Shelves.CURRENTLY_READING, Shelves.READ]
        self.next_shelf()

        return self.create_url(), None

    def next_shelf(self):
        try:
            self.shelf = self.shelves.pop(0)
        except IndexError:
            self.shelf = None

    def parse_content(self, content):
        return xmltodict.parse(content.decode('utf-8'))

    def parse(self, data):
        items = data['rss']['channel'].get('item', [])

        # xmltodict parses item as a dict if theres only one item
        if isinstance(items, dict):
            items = [items]

        if self.shelf == Shelves.CURRENTLY_READING and len(items) > 1:
            raise InvalidShelvesState(
                'More than 2 books exist (%d) on %s shelf' % (
                    len(items),
                    Shelves.CURRENTLY_READING
                )
            )

        events = [
            self.to_event(item) for item in items
            # on the read shelf, ignore books added directly.
            if self.shelf != Shelves.READ or item["user_read_at"] is not None
        ]

        self.next_shelf()

        return events, self.create_url(), None
