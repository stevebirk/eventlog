import datetime

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields


class Behance(Feed):

    key_field = Fields.LINK

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://www.behance.net/v2/users/%s/appreciations' % (
            self.config['username']
        )

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']

        self._page = 1

    def _make_url(self):
        url = self.url + ("?access_token=%s" % (self._ACCESS_TOKEN))

        if self._page > 1:
            url += ("&page=%s" % (str(self._page)))

        return url

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['project']['name']
        e.link = raw['project']['url']
        e.occurred = datetime.datetime.utcfromtimestamp(raw['timestamp'])

        # get largest cover
        sizes = sorted(
            [int(size) for size in raw['project']['covers']
             if size != 'original']
        )
        largest = sizes[-1]

        e.thumbnail_url = raw['project']['covers'][str(largest)]
        e.original_url = raw['project']['covers'][str(largest)]
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self._make_url(), None

    def parse(self, data):
        events = [self.to_event(a) for a in data['appreciations']]

        num_returned = len(data['appreciations'])
        next_url = None
        next_headers = None

        if num_returned > 0:
            self._page += 1
            next_url = self._make_url()

        return events, next_url, next_headers
