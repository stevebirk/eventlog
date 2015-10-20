import json
import datetime
import pytz
import logging

import oauth2 as oauth

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields

_LOG = logging.getLogger(__name__)


def _should_make_request(dt):
    # get datetime for now in UTC
    now = pytz.utc.localize(datetime.datetime.utcnow())

    # create requests for dates that are within nextdate + 10m
    return (dt + datetime.timedelta(hours=5, days=1) < now)


class DateMissing(Exception):
    pass


class Fitbit(Feed):

    rate_limit = 150.0 / (60 * 60)  # 150 per hour

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.fitbit.com'
        self.uri = '/1/user/-/activities/date/%Y-%m-%d.json'

        # OAuth
        self._CONSUMER_KEY = self.config['oauth1_consumer_key']
        self._CONSUMER_SECRET = self.config['oauth1_consumer_secret']
        self._USER_KEY = self.config['oauth1_user_key']
        self._USER_SECRET = self.config['oauth1_user_secret']
        self._ENCODED_USER_ID = self.config['encoded_user_id']
        self._SIGNUP_DATE = self.config['signup_date']
        self.consumer = oauth.Consumer(
            self._CONSUMER_KEY, self._CONSUMER_SECRET
        )
        self.signature_method = oauth.SignatureMethod_HMAC_SHA1()
        self.token = oauth.Token(key=self._USER_KEY, secret=self._USER_SECRET)

        # convert SIGNUP_DATE to naive UTC datetime
        self.signup_date = self.timezone.localize(
            datetime.datetime.strptime(self._SIGNUP_DATE, "%Y-%m-%d")
        ).astimezone(pytz.utc).replace(tzinfo=None)

        self.next_date = None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.text = Fitbit.get_text(raw)
        e.occurred = datetime.datetime.strptime(
            raw['datetime'], '%a %b %d %H:%M:%S +0000 %Y'
        )
        e.raw = raw

        return e

    @staticmethod
    def get_text(raw):

        distance = -1
        for i in raw['summary']['distances']:
            if i['activity'] == 'total':
                distance = i['distance']

        template = ', '.join([
            '%d steps taken',
            '%d floors climbed',
            '%.2f km traveled',
            '%d calories burned'
        ])

        text = template % (
            raw['summary']['steps'],
            raw['summary']['floors'],
            distance,
            raw['summary']['caloriesOut']
        )

        # use activeScore if available
        activeScore = raw['summary']['activeScore']
        if activeScore > -1:
            text += ', %d active score' % (activeScore)

        return text

    def _make_request(self):

        # convert nextdate to our local timezone
        nextdate_local = self.timezone.normalize(
            self.next_date.astimezone(self.timezone)
        )

        # create request
        uri = nextdate_local.strftime(self.uri)

        request_url = self.url + uri

        oauth_request = oauth.Request.from_consumer_and_token(
            self.consumer, token=self.token, http_url=request_url
        )

        oauth_request.sign_request(
            self.signature_method, self.consumer, self.token
        )

        return request_url, oauth_request.to_header()

    def init_parse_params(self, **kwargs):

        # next request is last_updated + 1
        last_updated = kwargs.get('last_updated', self.signup_date)

        self.next_date = last_updated + datetime.timedelta(days=1)
        self.next_date = pytz.utc.localize(self.next_date)

        if not _should_make_request(self.next_date):
            return None, None

        return self._make_request()

    def parse(self, data):

        if 'datetime' not in data and self.next_date is not None:
            data['datetime'] = self.next_date.strftime(
                '%a %b %d %H:%M:%S %z %Y'
            )
        else:
            self.next_date = datetime.datetime.strptime(
                data['datetime'], '%a %b %d %H:%M:%S +0000 %Y'
            )

        events = [self.to_event(data)]

        self.next_date += datetime.timedelta(days=1)
        next_url, next_headers = None, None

        if _should_make_request(self.next_date):
            next_url, next_headers = self._make_request()

        return events, next_url, next_headers
