import abc
import math
import datetime

from collections import namedtuple

from psycopg2 import DataError

import whoosh.query
from whoosh.qparser import QueryParser, MultifieldParser

from eventlog.lib.events import Event
from eventlog.lib.util import local_datetime_to_utc, utc_datetime_to_local

from .pagination import Page, InvalidPage, ByTimeRangeCursor, BySearchCursor


class EventSet(metaclass=abc.ABCMeta):

    def __init__(self, pool, eventquery, pagesize, timezone=None):
        self.pagesize = pagesize
        self.timezone = timezone

        self._eventquery = eventquery
        self._pool = pool
        self._cursor = None

        # local cache of event count
        self.__count = None

    @property
    def count(self):
        return len(self)

    @property
    def num_pages(self):
        return int(math.ceil(self.count / float(self.pagesize)))

    def __len__(self):
        if self.__count is None:
            self.__count = self._count()

        return self.__count

    @abc.abstractmethod
    def __iter__(self):  # pragma: no cover
        # should iterate through all events in the set
        pass

    @abc.abstractmethod
    def _count(self):  # pragma: no cover
        # returns total count of events
        pass

    @abc.abstractmethod
    def page(self, cursor=None):  # pragma: no cover
        pass

    def pages(self, cursor=None):

        p = self.page(cursor)

        yield p

        while p.next is not None:
            p = self.page()

            yield p


class EventSetByQuery(EventSet):

    def _count(self):
        # reset query limit
        self._eventquery.set_limit(None)

        with self._pool.connect() as cur:

            # only use the basequery to determine count
            cur.execute(
                "select count(*) from ({basequery}) t".format(
                    basequery=self._eventquery.basequery
                ),
                self._eventquery.basequery.params
            )

            return int(cur.fetchone()[0])

    @property
    def num_pages(self):
        num = super().num_pages

        if (self.count % self.pagesize) == 0:
            num += 1

        return num

    def __iter__(self):
        # reset query limit
        self._eventquery.set_limit(None)

        with self._pool.connect() as cur:

            # executing as iterable, get all
            cur.execute(self._eventquery.query, self._eventquery.params)

            for r in cur:
                e = Event.from_dict(r[0])

                if self.timezone is not None:
                    e.localize(self.timezone)

                yield e

    def page(self, cursor=None):

        # move cursor if provided
        if cursor is not None:
            self._cursor = cursor

        # set query cursor
        self._eventquery.set_cursor(self._cursor)

        # set query limit
        self._eventquery.set_limit(self.pagesize)

        # perform query
        with self._pool.connect() as cur:
            cur.execute(self._eventquery.query, self._eventquery.params)

            events = [Event.from_dict(r[0]) for r in cur]

        # if there were at least pagesize events, set up next page
        if len(events) == self.pagesize:
            self._cursor = ByTimeRangeCursor(
                events[-1].occurred,
                events[-1].id
            )

        # otherwise, indicate there is no next page, and reset internal cursor
        else:
            self._cursor = None

        return Page(events, self._cursor, timezone=self.timezone)


SearchMetadata = namedtuple('Metadata', ['count', 'latest'])


class EventSetBySearch(EventSet):

    def __init__(self, index, pool, query, eventquery, pagesize, timezone=None,
                 to_mask=None, to_filter=None, before=None, after=None):

        super().__init__(pool, eventquery, pagesize, timezone=timezone)

        self._index = index

        self._filter_terms = None
        self._mask_terms = None

        self._metadata = SearchMetadata(0, None)

        self.query = query

        self.before = before
        self.after = after

        # convert any provided timestamps to UTC
        if self.before is not None:
            self.before = local_datetime_to_utc(self.before, self.timezone)

        if self.after is not None:
            self.after = local_datetime_to_utc(self.after, self.timezone)

        parser = MultifieldParser(["title", "text"], self._index.schema)

        self._parsed_query = parser.parse(self.query)

        # build feed filters and masks
        if to_filter is not None:
            self._filter_terms = whoosh.query.Or(
                [whoosh.query.Term("feed", str(feed)) for feed in to_filter]
            )

        if to_mask is not None:
            self._mask_terms = whoosh.query.Or(
                [whoosh.query.Term("feed", str(feed)) for feed in to_mask]
            )

        # build daterange filter
        if self.before is not None or self.after is not None:

            # default after is a very early timestamp
            after = (
                self.after
                if self.after is not None
                else datetime.datetime.utcfromtimestamp(1)
            )

            # default before is the current timestamp
            before = (
                self.before
                if self.before is not None
                else datetime.datetime.utcnow()
            )

            filter_term = whoosh.query.DateRange(
                "occurred",
                after,
                before,
                startexcl=True,
                endexcl=True
            )

            if self._filter_terms is None:
                self._filter_terms = filter_term
            else:
                self._filter_terms &= filter_term

        # determine metadata
        self._search_metadata()

    @property
    def latest(self):
        if self._metadata.latest is not None:
            return utc_datetime_to_local(self._metadata.latest, self.timezone)

    def _count(self):
        return self._metadata.count

    def _search_metadata(self, sortedby="occurred", reverse=True):
        with self._index.searcher() as searcher:
            # search!
            hits = searcher.search_page(
                self._parsed_query,
                1,
                filter=self._filter_terms,
                mask=self._mask_terms,
                pagelen=self.pagesize,
                sortedby=sortedby,
                reverse=reverse
            )

            if hits:
                # data stored in Whooosh is already UTC
                self._metadata = SearchMetadata(
                    hits.total,
                    hits[0]["occurred"]
                )

    def _search_page(self):

        if self._cursor is None:
            # set initial cursor
            self._cursor = BySearchCursor(1)

        with self._index.searcher() as searcher:

            # search!
            hits = searcher.search_page(
                self._parsed_query,
                self._cursor.page,
                filter=self._filter_terms,
                mask=self._mask_terms,
                pagelen=self.pagesize
            )

            if not hits and self._cursor.page == 1:
                return []
            elif not hits:
                raise InvalidPage

            event_ids = tuple([hit["id"] for hit in hits])

            events = {}

            # get events from db
            with self._pool.connect() as cur:
                cur.execute(self._eventquery.query, (event_ids, ))

                # maintain ordering by score
                for r in cur:
                    e = Event.from_dict(r[0])
                    events[e.id] = e

            return [events[i] for i in event_ids]

    def __iter__(self):
        for _ in range(1, self.num_pages + 1):
            yield from self.page()

    def page(self, cursor=None):

        # set cursor
        if cursor is not None:
            self._cursor = cursor

        events = self._search_page()

        # increment page in cursor
        self._cursor.page += 1

        # indicate there is no next page, reset internal cursor
        if self._cursor.page > self.num_pages:
            self._cursor = None

        return Page(events, self._cursor, timezone=self.timezone)
