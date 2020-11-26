import logging
import datetime
import uuid

from eventlog.lib.events import Fields, InvalidField, MissingEventIDException
from eventlog.lib.feeds import Feed, MissingFeedIDException
from eventlog.lib.loader import load
from eventlog.lib.util import local_datetime_to_utc

from .pagination import ByTimeRangeCursor
from .eventquery import EventQuery
from .eventset import EventSetByQuery
from .search import Index
from .query import Query
from .pool import Pool

_LOG = logging.getLogger(__name__)


class Store:

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

        default_config.update(app.config.get('STORE', {}))

        self._config = default_config

        self._pool = Pool(
            self._config['DB_POOL_MIN_CONN'],
            self._config['DB_POOL_MAX_CONN'],
            self._config['DB_NAME'],
            self._config['DB_USER'],
            self._config['DB_PASS']
        )

        self._index = self._init_index()

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
        if not isinstance(field, Fields):
            raise InvalidField

        query = Query("select {events}.* from events {events}")
        query = query.add_clause("{events}." + str(field) + "=%s", (value, ))

        with self._pool.connect() as cur:
            cur.execute(query.format(), query.params)

            res = cur.fetchone()

        return True if res is not None else False

    def update_feeds(self, feeds, dry=False):
        with self._pool.connect(
            dry=dry,
            error_message="rolled back update feed changes"
        ) as cur:

            for f in feeds:

                _LOG.info("updating %s", str(f))

                cur.execute(
                    """
                    update feeds
                    set (full_name, short_name, favicon, color, module, config,
                         is_public, is_updating, is_searchable) =
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    where id = %s
                    """,
                    f.tuple()[1:] + (f.id, )
                )

                if not cur.rowcount:
                    raise MissingFeedIDException(
                        "Feed with ID '%s' does not exist" % (f.id)
                    )

    def add_events(self, events, dry=False):

        with self._pool.connect(
            dry=dry,
            error_message="rolled back new event changes"
        ) as cur:

            for e in events:

                cur.execute(
                    """
                    insert into events
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict do nothing
                    """,
                    e.tuple()
                )

                if not cur.rowcount:
                    _LOG.warning('skipping existing event id=%s', e.id)

                if e.related is not None:
                    for c in e.related:

                        # this is needed for .tuple call below to
                        # succeed for events fetched from the store since their
                        # related events have no feed data
                        if c.feed is None:
                            c.feed = e.feed

                        # if the event already exists need is_related to be set
                        # properly
                        cur.execute(
                            """
                            insert into events
                            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            on conflict (id) do update
                            set is_related = excluded.is_related
                            """,
                            c.tuple(is_related=True)
                        )

                        cur.execute(
                            """
                            insert into related_events (parent, child)
                            values (%s, %s)
                            on conflict do nothing
                            """,
                            (e.id, c.id)
                        )

                _LOG.info("saved %s", str(e))

        # index new events
        self._index.index(events, dry=dry)

    def update_events(self, events, dry=False):
        with self._pool.connect(
            dry=dry,
            error_message="rolled back update event changes"
        ) as cur:

            for e in events:

                cur.execute(
                    """
                    update events
                    set (title, text, link, occurred,
                         raw, thumbnail, original, archived) =
                        (%s, %s, %s, %s, %s, %s, %s, %s)
                    where id = %s
                    """,
                    e.tuple()[2:-1] + (e.id, )
                )

                if not cur.rowcount:
                    raise MissingEventIDException(
                        "Event with ID '%s' does not exist" % (e.id)
                    )

                _LOG.info("updated %s", str(e))

        # re-index events
        self._index.index(events, dry=dry)

    def remove_events(self, events=None, feed=None, dry=False):

        if events is None and feed is None:
            return

        with self._pool.connect(
            dry=dry,
            error_message="rolled back remove event changes"
        ) as cur:

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

                    _LOG.info("removed %s", str(e))

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

        # remove index values here
        self._index.remove(events=events, feed=feed, dry=dry)

    def get_feeds(self, include_admin=False, **kwargs):
        flags = ['is_public', 'is_updating', 'is_searchable']

        config = {}

        # prepare query
        query = Query("select * from feeds")

        for flag, value in kwargs.items():
            if flag in flags:
                query = query.add_clause(flag + "=%s", (value,))

        # grab feeds from database
        with self._pool.connect(dict_cursor=True) as cur:

            cur.execute(query.format(), query.params)

            for row in cur:
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

    def get_events_by_ids(self, ids, pagesize=10, timezone=None,
                          embed_feeds=True, embed_related=True):

        basequery = Query("select {events}.* from events {events}")

        eq = EventQuery(
            basequery,
            embed_feeds=embed_feeds,
            embed_related=embed_related
        )

        # validate provided IDs as UUIDs
        validated = []

        for i in ids:
            try:
                uuid.UUID(i)

                validated.append(i)
            except ValueError:
                pass

        if validated:
            eq.add_clause("{events}.id in %s", (tuple(set(validated)), ))
        else:
            # want an empty result set if no valid IDs were provided
            eq.add_clause("(\"id\" != \"id\")")

        es = EventSetByQuery(self._pool, eq, pagesize, timezone=timezone)

        return es

    def get_events_by_latest(self, feed=None, timezone=None, pagesize=10,
                             embed_related=True):

        basequery = Query("""
            select {events}.*
            from events {events}
            inner join (
                select distinct on (feed_id) id
                from events where is_related=false
                order by feed_id, occurred desc
            ) latest on latest.id = {events}.id
        """)

        if feed is not None:
            basequery += (
                "inner join feeds {feeds} on {events}.feed_id = {feeds}.id"
            )

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=embed_related
        )

        if feed is not None:
            eq.add_clause("{feeds}.short_name = %s", (feed,))

        es = EventSetByQuery(self._pool, eq, pagesize, timezone=timezone)

        events = list(es)

        if feed is None:
            return {e.feed['short_name']: e for e in events}
        elif events:
            return events[0]
        else:
            return None

    def get_events_by_date(self, d, feeds=None, **kwargs):

        # start of day
        dt = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, 0)

        after = dt - datetime.timedelta(microseconds=1)
        before = dt + datetime.timedelta(days=1)

        return self.get_events_by_timerange(
            before=before,
            after=after,
            feeds=feeds,
            **kwargs
        )

    def get_events_by_timerange(self, before=None, after=None, pagesize=10,
                                feeds=None, flattened=False, timezone=None,
                                embed_related=True):

        basequery = Query("select {events}.* from events {events}")

        if feeds is not None:
            basequery += ", feeds {feeds} where {events}.feed_id={feeds}.id"

        if flattened:
            embed_related = False

        eq = EventQuery(
            basequery,
            embed_feeds=True,
            embed_related=embed_related
        )

        if before is not None:
            eq.add_clause(
                "{events}.occurred < %s",
                (local_datetime_to_utc(before, timezone),)
            )

        if after is not None:
            eq.add_clause(
                "{events}.occurred > %s",
                (local_datetime_to_utc(after, timezone),)
            )

        if feeds is not None:
            eq.add_clause("{feeds}.short_name in %s", (tuple(feeds),))

        if not flattened:
            eq.add_clause("{events}.is_related=false")

        return EventSetByQuery(self._pool, eq, pagesize, timezone=timezone)

    def get_events_by_search(self, query, pagesize=10, **kwargs):

        basequery = Query(
            "select {events}.* from events {events} where {events}.id in %s"
        )

        eq = EventQuery(basequery, embed_feeds=True, embed_related=False)

        return self._index.search(query, eq, self._pool, pagesize, **kwargs)
