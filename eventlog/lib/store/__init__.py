import time
import math
import logging
import datetime
import pytz

import psycopg2
import psycopg2.pool
import psycopg2.extras
import psycopg2.extensions

from eventlog.lib.events import fields, InvalidField, MissingEventIdException
from eventlog.lib.feeds import Feed
from eventlog.lib.loader import load
from eventlog.lib.util import tz_unaware_local_dt_to_utc

from .pagination import Page
from .eventquery import EventQuery
from .eventset import EventSet
from .search import Index

_LOG = logging.getLogger(__name__)

psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)


class InvalidTimeRangeException(Exception):
    pass


def _event_to_tuple(e, is_related=False):
    return (e.id,
            e.feed['id'],
            e.title,
            e.text,
            e.link,
            e.occurred,
            e.raw,
            e.thumbnail,
            e.original,
            e.archived,
            is_related)


def _id_exists(cur, event_id):
    cur.execute(
        "select count(id) from events where id=%s",
        (event_id, )
    )

    return bool(cur.fetchone()[0])


class Store(object):

    def __init__(self):
        self._pool = None
        self._config = None
        self._index = None

    def init_app(self, app):

        default_config = {
            'DB_USER': 'eventlog',
            'DB_PASS': 'eventlog',
            'DB_NAME': 'eventlog',
            'DB_POOL_MIN_CONN': 10,
            'DB_POOL_MAX_CONN': 20,
            'INDEX_DIR': None,
            'MEDIA_DIR': None,
            'THUMBNAIL_SUBDIR': 'thumbs',
            'THUMBNAIL_WIDTH': 200,
            'THUMBNAIL_HEIGHT': 200,
            'ORIGINAL_SUBDIR': 'originals',
            'ARCHIVE_SUBDIR': 'archives',
            'TIME_ZONE': 'UTC'
        }

        default_config.update(
            app.config.get('STORE', {})
        )

        self._config = default_config
        self._pool = self._init_pool()
        self._index = self._init_index()

    def _init_pool(self):
        return psycopg2.pool.ThreadedConnectionPool(
            self._config['DB_POOL_MIN_CONN'],
            self._config['DB_POOL_MAX_CONN'],
            database=self._config['DB_NAME'],
            user=self._config['DB_USER'],
            password=self._config['DB_PASS']
        )

    def _init_index(self):
        if self._config['INDEX_DIR'] is None:
            _LOG.warning(
                'Indexing disabled, please specify INDEX_DIR in config.'
            )
            return None
        else:
            index = Index(self._config['INDEX_DIR'])
            return index

    def exists(self, field, value):

        # verify field is valid
        if field not in fields:
            raise InvalidField

        basequery = "select * from events where " + str(field) + "=%s"
        params = (value,)

        eq = EventQuery(
            basequery, params,
            embed_feeds=False,
            embed_related=False
        )

        conn = self._pool.getconn()
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute(eq.query, eq.params)
            res = cur.fetchone()
            cur.close()
        finally:
            self._pool.putconn(conn)

        return True if res is not None else False

    def add_events(self, events, dry=False):

        conn = self._pool.getconn()
        conn.autocommit = False
        try:
            cur = conn.cursor()

            for e in events:

                if not _id_exists(cur, e.id):
                    cur.execute(
                        """
                        insert into events
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        _event_to_tuple(e)
                    )
                else:
                    _LOG.warning('skipping existing event id=%s', e.id)

                if e.related is not None:
                    for c in e.related:

                        if _id_exists(cur, c.id):
                            # TODO: this will currently just ignore the
                            #       existing event, rather then modify it
                            #       or even mark it as related
                            _LOG.warning(
                                'skipping existing related event id=%s', c.id
                            )
                            continue

                        cur.execute(
                            """
                            insert into events
                            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            _event_to_tuple(c, is_related=True)
                        )

                        cur.execute(
                            """
                            insert into related_events (parent, child)
                            values (%s, %s)
                            """,
                            (e.id,
                             c.id)

                        )

                _LOG.info("saved %s", unicode(e))

            if not dry:
                conn.commit()
            else:
                conn.rollback()

        except Exception:  # catches psycopg2.Error
            conn.rollback()
            _LOG.error('rolled back new event changes')
            raise
        finally:
            self._pool.putconn(conn)

        # index new events
        self._index.index(events, dry=dry)

    def update_events(self, events, dry=False):
        conn = self._pool.getconn()
        conn.autocommit = False
        try:
            cur = conn.cursor()

            for e in events:

                if not _id_exists(cur, e.id):
                    raise MissingEventIdException(
                        "Event with ID '%s' does not exist" % (e.id)
                    )

                cur.execute(
                    """
                    update events
                    set (title, text, link, occurred,
                         raw, thumbnail, original, archived) =
                        (%s, %s, %s, %s, %s, %s, %s, %s)
                    where id = %s
                    """,
                    _event_to_tuple(e)[2:-1] + (e.id, )
                )

                _LOG.info("updated %s", unicode(e))

            if not dry:
                conn.commit()
            else:
                conn.rollback()

        except Exception:
            conn.rollback()
            _LOG.error('rolled back update event changes')
            raise
        finally:
            self._pool.putconn(conn)

        # re-index events
        self._index.index(events, dry=dry)

    def remove_events(self, events=None, feed=None, dry=False):

        if events is None and feed is None:
            return

        conn = self._pool.getconn()
        conn.autocommit = False
        try:
            cur = conn.cursor()

            if events is not None:  # delete specified events
                for e in events:
                    if e.related is not None:
                        cur.execute(
                            "delete from related_events where parent=%s",
                            (e.id,)
                        )

                        for c in e.related:
                            cur.execute(
                                "delete from events where id=%s", (c.id,)
                            )

                    cur.execute("delete from events where id=%s", (e.id,))

                    _LOG.info("removed %s", unicode(e))

            elif feed is not None:
                cur.execute(
                    """
                    delete from events
                    where feed_id in (
                        select id from feeds where short_name = %s
                    )
                    """,
                    (feed, )
                )

                _LOG.info("removed all events for feed %s", feed)

            if not dry:
                conn.commit()
            else:
                conn.rollback()

        except Exception:
            conn.rollback()
            _LOG.error('rolled back remove event changes')
            raise
        finally:
            self._pool.putconn(conn)

        # remove index values here
        self._index.remove(events=events, feed=feed, dry=dry)

    def get_feeds(self, include_admin=False, **kwargs):
        flags = ['is_public', 'is_updating', 'is_searchable']

        basequery = "select * from feeds"
        clauses = []
        params = ()

        for flag, value in kwargs.items():
            if flag in flags:
                clauses.append(flag + "=%s")
                params += (value,)

        query = basequery
        if len(clauses):
            query += " where "
            query += " and ".join(clauses)

        # grab feeds from database
        conn = self._pool.getconn()
        conn.autocommit = True
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            self._pool.putconn(conn)

        config = {}

        for row in rows:
            module = row['module']

            overrides = row['config']
            del row['config']

            config[module] = {
                key: row[key] for key in row if not key.startswith('is_')
            }
            config[module]['flags'] = {
                flag: row[flag] for flag in row if flag.startswith('is_')
            }
            config[module]['overrides'] = overrides

            config[module]['default'] = {
                key.lower(): self._config[key]
                for key in self._config if not key.startswith('DB_')
            }

        # load feeds
        feeds = load(Feed, config, store=self)

        return {feed.short_name: feed for feed in feeds}

    def get_events(self, feeds=None, **kwargs):

        if feeds is None:
            basequery = "select * from events where is_related=false"
        else:
            basequery = """
                select events.* from events, feeds
                where events.feed_id=feeds.id and is_related=false
            """

        if kwargs.get('flattened', False):
            kwargs['embed_related'] = False
            basequery = basequery.replace(' and is_related=false', '')
            basequery = basequery.replace('where is_related=false', '')

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=kwargs.get('embed_related', True)
        )

        if feeds is not None:
            eq.add_clause("short_name in %s", (tuple(feeds),))

        es = EventSet(
            self._pool,
            eq,
            kwargs.get('pagesize', 10),
            timezone=kwargs.get('timezone'))

        return es

    def get_events_by_ids(self, ids, **kwargs):

        basequery = "select * from events where id in %s"
        params = (tuple(ids), )

        eq = EventQuery(
            basequery, params,
            embed_feeds=kwargs.get('embed_feeds', True),
            embed_related=kwargs.get('embed_related', True)
        )

        es = EventSet(
            self._pool,
            eq,
            kwargs.get('pagesize', 10),
            timezone=kwargs.get('timezone'))

        return es

    def get_events_by_latest(self, feed=None, timezone=None, **kwargs):

        basequery = """
            select e.*
            from events e
            inner join (
                select distinct on (feed_id) id
                from events where is_related=false
                order by feed_id, occurred desc
            ) latest on latest.id = e.id
        """

        if feed is not None:
            basequery += "inner join feeds f on e.feed_id = f.id"

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=kwargs.get('embed_related', True)
        )

        if feed is not None:
            eq.add_clause("f.short_name = %s", (feed,))

        es = EventSet(
            self._pool,
            eq,
            kwargs.get('pagesize', 10),
            timezone=timezone)

        if feed is None:
            # TODO: should return dict of feed: latest
            return es
        else:
            if es.count == 1:
                return list(es)[0]
            else:
                return None

    def get_events_by_date(self, d, feeds=None, **kwargs):

        # start of day
        start = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, 0)

        # end of day
        end = datetime.datetime(d.year, d.month, d.day, 23, 59, 59, 999999)

        return self.get_events_by_timerange(start, end, feeds, **kwargs)

    def get_events_by_timerange(self, start=None, end=None, feeds=None,
                                **kwargs):

        if feeds is None:
            basequery = "select * from events where is_related=false"
        else:
            basequery = """
                select events.* from events, feeds
                where events.feed_id=feeds.id and is_related=false
            """

        if kwargs.get('timezone'):
            # implies dates are localized, need to convert to UTC
            tz = pytz.timezone(kwargs.get('timezone'))
            start = tz_unaware_local_dt_to_utc(start, tz)

            if end is not None:
                end = tz_unaware_local_dt_to_utc(end, tz)

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=kwargs.get('embed_related', True)
        )

        if start is not None and end is not None:
            eq.add_clause("occurred between %s and %s", (start, end))
            eq.add_sort("occurred", "asc")
        elif start is not None:
            eq.add_clause("occurred >= %s", (start,))
            eq.add_sort("occurred", "asc")
        elif end is not None:
            eq.add_clause("occurred <= %s", (end,))
            eq.add_sort("occurred")
        else:
            raise InvalidTimeRangeException('must specify start and/or end')

        if feeds is not None:
            eq.add_clause("short_name in %s", (tuple(feeds),))

        es = EventSet(
            self._pool,
            eq,
            kwargs.get('pagesize', 10),
            timezone=kwargs.get('timezone'))

        return es

    def get_events_by_search(self, query, timezone=None, **kwargs):
        basequery = "select * from events where id in %s"

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=False
        )

        es = self._index.search(
            query,
            eq,
            self._pool,
            timezone=timezone,
            **kwargs
        )

        return es
