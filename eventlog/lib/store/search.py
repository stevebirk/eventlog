import os
import math
import logging

from threading import RLock

from .pagination import Page
from .eventset import EventSetBySearch

from whoosh.index import open_dir, exists_in, create_in
from whoosh.fields import *

_LOG = logging.getLogger(__name__)

_LOCK = RLock()

_SCHEMA = Schema(
    id=ID(unique=True, stored=True),
    feed=ID,
    text=TEXT,
    title=TEXT
)


def open_index(path, force_new=False):

    index = None

    try:
        if exists_in(path) and not force_new:
            index = open_dir(path)
            _LOG.debug("loaded search index from '%s'", path)
        else:
            if not os.path.exists(path):
                _LOG.info('creating non-existent index directory: %s', path)
                os.mkdir(path)

            index = create_in(path, _SCHEMA)

    except Exception:
        _LOG.exception("Unable to get search index at '%s'", path)

    return index


class Index(object):

    def __init__(self, index_dir):
        self._indexref = None
        self._index_dir = index_dir

    @property
    def _index(self):
        if self._indexref is None:
            self._indexref = open_index(self._index_dir)

        return self._indexref

    def clear(self, path=None):

        if path is None:
            path = self._index_dir

        self._indexref = open_index(path, force_new=True)

    def index(self, events, dry=False):
        # if no index initialized, do nothing
        if self._index is None or len(events) == 0:
            return

        _LOCK.acquire()

        writer = self._index.writer()

        for e in events:
            for doc in e.documents:
                writer.update_document(**doc)

            num_related = 0 if e.related is None else len(e.related)

            _LOG.info(
                "indexed %s and %d related events",
                str(e),
                num_related
            )

        if not dry:
            writer.commit()
            _LOG.info("index updates committed")
        else:
            writer.cancel()

        _LOCK.release()

    def remove(self, events=None, feed=None, dry=False):
        # if no index initialized, do nothing
        if self._index is None:
            _LOG.debug(
                'remove called with no index initialized, nothing to remove'
            )
            return

        if events is None and feed is None:
            _LOG.debug('received nothing to remove')
            return

        _LOCK.acquire()

        writer = self._index.writer()

        if events is not None:
            for e in events:
                for doc in e.documents:
                    writer.delete_by_term('id', doc['id'])

                num_related = 0 if e.related is None else len(e.related)

                _LOG.info(
                    "remove indexed %s and %d related events",
                    str(e),
                    num_related
                )

        elif feed is not None:
            writer.delete_by_term('feed', feed)
            _LOG.info("removed all documents for feed '%s'", feed)

        if not dry:
            writer.commit()
            _LOG.info("index removals committed")
        else:
            writer.cancel()

        _LOCK.release()

    def search(self, query, eventquery, pool, pagesize=10,
               to_filter=None, to_mask=None, timezone=None):

        if self._index is None:
            return

        return EventSetBySearch(
            self._index,
            pool,
            query,
            eventquery,
            pagesize,
            timezone=timezone,
            to_mask=to_mask,
            to_filter=to_filter
        )
