import datetime

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields


class Foursquare(Feed):

    rate_limit = 500.0 / (60 * 60)  # 500 per hour

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.foursquare.com/v2/users/self/checkins'
        self._versioning = "20130329"

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']

        self.offset = 20
        self.limit = 20

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = Foursquare.get_title(raw)
        e.link = Foursquare.get_link(raw)
        e.occurred = datetime.datetime.utcfromtimestamp(
            float(raw['createdAt'])
        )
        e.thumbnail_url = Foursquare.get_image_url(raw)
        e.raw = raw

        return e

    def _make_url(self, offset=None):
        url = self.url + ('?oauth_token=%s&v=%s' % (
            self._ACCESS_TOKEN, self._versioning)
        )

        if offset is not None:
            url += ("&offset=%d&limit=100" % (offset))

        return url

    def init_parse_params(self, **kwargs):
        return self._make_url(), None

    def parse(self, data):

        events = [
            self.to_event(checkin)
            for checkin in data['response']['checkins']['items']
            if checkin['type'] in ['checkin', 'venueless']
        ]

        found = len(data['response']['checkins']['items'])
        next_headers = None
        next_url = None

        if (found == self.limit):
            next_url = self._make_url(self.offset)
            self.offset += 100
            self.limit = 100

        return events, next_url, next_headers

    @staticmethod
    def get_title(entry):
        if entry['type'] == 'checkin':
            return entry['venue']['name']
        else:
            return entry['location']['name']

    @staticmethod
    def get_link(entry):
        if entry['type'] == 'checkin':
            return "https://foursquare.com/v/%s" % entry['venue']['id']
        else:
            return None

    @staticmethod
    def get_image_url(entry):

        link = Foursquare.get_link(entry)
        if link is not None:
            link = link + '/photos'
        return link
