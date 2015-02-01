import datetime
import logging

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields

_LOG = logging.getLogger(__name__)


class Lastfm(Feed):

    grouped = True
    grouped_window = 60 * 60

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        base = "http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks"

        self.url = base + "&user=%s&api_key=%s&limit=%d&format=json" % (
            self.config['username'],
            self.config['api_key'],
            self.config['num_limit']
        )

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.text = raw['artist']['#text'] + " - " + raw['name']
        e.link = raw.get('url')
        e.occurred = datetime.datetime.utcfromtimestamp(
            float(raw["date"]["uts"])
        )
        e.thumbnail_url = Lastfm.get_image_url(raw)
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, None

    def parse(self, data):
        events = []
        for track in data['recenttracks']['track']:
            # make sure this is not a "nowplaying" track
            attributes = track.get('@attr')

            if attributes and (attributes.get('nowplaying') == 'true'):
                continue

            events.append(self.to_event(track))

        total_pages = int(data['recenttracks']['@attr']['totalPages'])

        next_page = int(data['recenttracks']['@attr']['page']) + 1
        next_url = None
        next_headers = None

        if next_page <= total_pages:
            next_url = self.url + ("&page=%d" % (next_page))

        return events, next_url, next_headers

    @staticmethod
    def get_image_url(entry):
        url = None
        try:
            url = entry['image'][-1]['#text']
        except Exception:
            _LOG.exception("unable to parse image url")

        if not url:
            url = None

        return url

    def get_key_func(self):

        def func(e):
            datefmt = '%a %b %d %H:%M:%S %Y'
            return (e.text, e.occurred.strftime(datefmt))

        return func
