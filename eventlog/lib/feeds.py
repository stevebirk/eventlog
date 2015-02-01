import abc
import logging
import pytz
import json
import time
import httplib2

from .util import urlize
from .events import fields, DATEFMT

_LOG = logging.getLogger(__name__)


class HTTPRequestFailure(Exception):
    pass


class Feed(object):

    __metaclass__ = abc.ABCMeta

    # properties
    key_field = fields.OCCURRED
    grouped = False
    grouped_window = None
    rate_limit = 1

    def __init__(self, config, **kwargs):

        # set config
        self.config = config.get('default', {})
        self.overrides = config.get('overrides')
        if self.overrides is not None:
            self.config.update(self.overrides)

        self.color = config.get('color', '000000')
        self.short_name = config.get('short_name')
        self.full_name = config.get('full_name')
        self.favicon = config.get('favicon')
        self.flags = config.get('flags')
        self.id = config.get('id')
        self.module = config.get('module')

        # set store
        self.store = kwargs.get('store')

        # local timezone
        self.timezone = pytz.timezone(self.config.get('time_zone', 'UTC'))

    def dict(self, admin=False, base_uri=None):
        d = {
            'id': self.id,
            'short_name': self.short_name,
            'full_name': self.full_name,
            'color': self.color,
            'favicon': self.favicon
        }

        if base_uri is not None:
            urlize(d, base_uri, key='favicon')

        if admin:
            d['config'] = self.overrides
            d['flags'] = self.flags
            d['module'] = self.module

        return d

    @abc.abstractmethod
    def init_parse_params(self, **kwargs):  # pragma: no cover
        pass

    @abc.abstractmethod
    def parse(self, data):  # pragma: no cover
        pass

    @abc.abstractmethod
    def to_event(self, raw):  # pragma: no cover
        pass

    def iter_events(self, **kwargs):

        load_all = kwargs.get('all', False)
        use_rate_limit = kwargs.get('rate_limit', False)

        if use_rate_limit:
            _LOG.info(
                "rate limiting requests to %.0f second(s) per req",
                1.0 / self.rate_limit
            )

        # re-use http connection
        conn = httplib2.Http(cache=self.config.get('http_cache'))

        # get initial request URL and headers
        next_url, next_headers = self.init_parse_params(**kwargs)

        while next_url:
            _LOG.debug("making request to: %s", next_url)

            resp, content = conn.request(next_url, "GET", headers=next_headers)

            if resp.status != 200:
                raise HTTPRequestFailure(
                    'received non-200 status %s for url "%s":\n%s' % (
                        str(resp.status),
                        next_url,
                        content
                    )
                )

            data = json.loads(content)

            events, next_url, next_headers = self.parse(data)

            for e in events:
                yield e

            # if this feed is not keyed on the occurred time
            # and we have not explicitly requested all data, return early
            if not load_all and (self.key_field != fields.OCCURRED):
                break

            # if rate limiting is in effect, pause now
            if use_rate_limit:
                time.sleep(1.0 / self.rate_limit)

    def fetch(self, **kwargs):

        last_updated = kwargs.get('last_updated')
        last_key = kwargs.get('last_key')

        events = []

        for e in self.iter_events(**kwargs):

            if self.key_field != fields.OCCURRED:

                # attempt to grab event, if it doesn't exist, add it
                key_name = self.key_field.name
                key_val = self.key_field.get_from(e)

                if last_key is not None and (key_val == last_key):
                    _LOG.debug(
                        "%s matches last known value :'%s'. Stopping.",
                        key_name,
                        key_val
                    )
                    break

                exists = self.store.exists(key_name, key_val)

                if not exists:
                    events.append(e)
                else:  # pragma: no cover
                    _LOG.debug(
                        "%s... already exists. Ignoring.",
                        unicode(e)
                    )

            else:   # add any events newer then the last entry for that source

                if (last_updated is None) or (e.occurred > last_updated):
                    events.append(e)
                else:
                    _LOG.debug("%s... is old.", unicode(e))
                    break

        return events

    def group(self, events, latest_event=None):

        if not self.grouped:
            return

        for e in sorted(events, key=lambda x: x.occurred):

            # no previous event, set group leader and latest datetime
            if latest_event is None:
                latest_event = e
                continue

            # get diff between this event and latest datetime
            diff = e.occurred - latest_event.latest_occurred

            # if we are within the windowing period, add it
            # as a child to our current latest event
            if (diff.seconds < self.grouped_window and diff.days == 0):

                # add new related
                latest_event.add_related(e)

                # add parent event if it doesn't exist
                if latest_event not in events:
                    events.append(latest_event)

                # remove this as an event to be added
                events.remove(e)

                _LOG.info("grouped %s", unicode(e))

            # otherwise we have a new group
            else:
                latest_event = e

    def update(self, dry=False):
        start = time.time()

        # get latest event for this feed
        latest_event = self.store.get_events_by_latest(feed=self.short_name)

        # retrieve latest updated datetime
        last_updated = None
        if latest_event is not None:
            last_updated = latest_event.latest_occurred
            _LOG.debug('last updated: %s', last_updated)
        else:
            _LOG.debug('no previous entries')

        try:
            # process new events
            events = self.fetch(last_updated=last_updated)

            # number of new events
            added = len(events)

            # fetch thumbnails
            for e in events:
                e.add_thumbnail(
                    self.config['thumbnail_width'],
                    self.config['thumbnail_height'],
                    self.config['media_dir'],
                    self.config['thumbnail_subdir'],
                    dry=dry
                )

                e.add_original(
                    self.config['media_dir'],
                    self.config['original_subdir'],
                    dry=dry
                )

                e.add_archive(
                    self.config['media_dir'],
                    self.config['archive_subdir'],
                    dry=dry
                )

            # do any grouping
            self.group(events, latest_event)

            # persist events
            self.store.add_events(events, dry=dry)

            if added > 0:
                _LOG.info("%d events added", added)

        except Exception:
            _LOG.exception('unable to process feed')
            added = 0

        end = time.time()
        _LOG.info('processing took %.6fs', end - start)

        return added

    def get_key_func(self):

        if self.key_field == fields.OCCURRED:
            def func(e):
                key_value = self.key_field.get_from(e)
                return key_value.strftime(DATEFMT)
        else:
            func = self.key_field.get_from

        return func

    def load(self, loadfile=None, dumpfile=None):

        events = []

        if loadfile is not None:
            fh = open(loadfile)
            for line in fh:
                data = json.loads(line)
                loaded, _, _ = self.parse(data)
                events += loaded

            events = sorted(events, key=lambda x: x.occurred)

            _LOG.info("%d events loaded from dump", len(events))

        latest_date = None
        latest_key = None

        if events:

            if self.key_field == fields.OCCURRED:
                latest_date = events[-1].latest_occurred
                _LOG.info('last known event from: %s', str(latest_date))
            else:
                latest_key = self.key_field.get_from(events[-1])
                _LOG.info(
                    'last known event with %s: %s',
                    self.key_field.name,
                    unicode(latest_key)
                )

        kwargs = {
            'rate_limit': True,
        }

        if latest_date is not None:
            kwargs['last_updated'] = latest_date
        else:
            kwargs['all'] = True

        if latest_key is not None:
            kwargs['last_key'] = latest_key

        from_remote = self.fetch(**kwargs)

        _LOG.info("%d events loaded from remote", len(from_remote))

        events += sorted(from_remote, key=lambda x: x.occurred)

        if dumpfile is not None:
            fh = open(dumpfile, 'w')

            try:
                for e in events:
                    fh.write('%s\n' % json.dumps(e.raw))
            finally:
                fh.close()

        return events

    def deep_search(self, e, existing):  # pragma: no cover
        return None

    def find_missing(self, missing):  # pragma: no cover
        return None
