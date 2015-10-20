import math

from psycopg2 import DataError

import whoosh.query
from whoosh.qparser import QueryParser, MultifieldParser

from eventlog.lib.events import Event

from .pagination import Page


class EventSet(object):

    def __init__(self, pool, eventquery, pagesize, timezone=None):

        self._pool = pool
        self._eventquery = eventquery

        self.pagesize = pagesize
        self.timezone = timezone

        conn = self._pool.getconn()
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute(
                "select count(*) from (" + self._eventquery.basequery + ") t",
                self._eventquery.baseparams
            )
            self.count = int(cur.fetchone()[0])
            cur.close()
        except DataError:
            self.count = 0
        finally:
            self._pool.putconn(conn)

        self.num_pages = int(math.ceil(self.count / float(self.pagesize)))

    def __iter__(self):
        conn = self._pool.getconn()
        conn.autocommit = True
        try:

            cur = conn.cursor()
            # executing as iterable, get all
            cur.execute(self._eventquery.query, self._eventquery.params)

            for r in cur:
                e = Event.from_dict(r[0])

                if self.timezone is not None:
                    e.localize(self.timezone)

                yield e
        finally:
            self._pool.putconn(conn)

    def __len__(self):
        return self.count

    def get_page(self, page):

        if self.num_pages == 0 and page == 1:
            return Page([], None, None, 0)

        if not (0 < page <= self.num_pages):
            return None

        offset = (page - 1) * self.pagesize

        if self._eventquery.sort is None:
            self._eventquery.add_sort('occurred')

        self._eventquery.add_limit(
            self.pagesize,
            offset if offset > 0 else None
        )

        conn = self._pool.getconn()
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute(self._eventquery.query, self._eventquery.params)
            rows = cur.fetchall()
        finally:
            self._pool.putconn(conn)

        events = [Event.from_dict(r[0]) for r in rows]

        if self.timezone is not None:
            [e.localize(self.timezone) for e in events]

        next_page = page + 1
        if next_page > self.num_pages:
            next_page = None

        prev_page = None
        if page > 1:
            prev_page = page - 1

        return Page(events, next_page, prev_page, self.count)


class EventSetBySearch(object):

    def __init__(self, index, pool, query, eventquery, pagesize, timezone=None,
                 to_mask=None, to_filter=None):
        self._eventquery = eventquery
        self._pool = pool
        self._index = index

        self.pagesize = pagesize
        self.timezone = timezone
        self.query = query

        parser = MultifieldParser(["title", "text"], self._index.schema)
        self._parsed_query = parser.parse(self.query)

        filter_terms = None
        if to_filter is not None:
            filter_terms = whoosh.query.Or(
                [
                    whoosh.query.Term("feed", str(feed))
                    for feed in to_filter
                ]
            )

        mask_terms = None
        if to_mask is not None:
            mask_terms = whoosh.query.Or(
                [whoosh.query.Term("feed", str(feed)) for feed in to_mask]
            )

        self._filter_terms = filter_terms
        self._mask_terms = mask_terms

        hits = self._search_page(1, to_events=False)
        if hits is not None:
            self.count = hits.total

            if to_filter is not None or to_mask is not None:
                self.count -= hits.results.filtered_count
        else:
            self.count = 0

        self.num_pages = int(math.ceil(self.count / float(self.pagesize)))

    def __len__(self):
        return self.count

    def _search_page(self, page, to_events=True):
        with self._index.searcher() as searcher:
            # search!
            hits = searcher.search_page(
                self._parsed_query, page,
                filter=self._filter_terms,
                mask=self._mask_terms,
                pagelen=self.pagesize
            )

            if not hits:
                return None

            if not to_events:
                return hits

            event_ids = tuple([hit["id"] for hit in hits])

            # get events from db
            conn = self._pool.getconn()
            conn.autocommit = True
            try:
                cur = conn.cursor()
                cur.execute(self._eventquery.query, (event_ids, ))
                rows = cur.fetchall()
            finally:
                self._pool.putconn(conn)

            events = [Event.from_dict(r[0]) for r in rows]

            if self.timezone is not None:
                [e.localize(self.timezone) for e in events]

            return events

    def get_page(self, page):

        if self.num_pages == 0 and page == 1:
            return Page([], None, None, 0)

        if not (0 < page <= self.num_pages):
            return None

        events = self._search_page(page)

        next_page = page + 1
        if next_page > self.num_pages:
            next_page = None

        prev_page = None
        if page > 1:
            prev_page = page - 1

        return Page(events, next_page, prev_page, self.count)
