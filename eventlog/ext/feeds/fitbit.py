import json
import datetime
import pytz
import urllib.parse
import httplib2
import logging
import base64

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event

_LOG = logging.getLogger(__name__)


def _should_make_request(dt):
    # get datetime for now in UTC
    now = pytz.utc.localize(datetime.datetime.utcnow())

    # create requests for dates that are within nextdate + 10m
    return (dt + datetime.timedelta(hours=5, days=1) < now)


class DateMissing(Exception):
    pass


class RefreshTokenFailure(Exception):
    pass


class Fitbit(Feed):

    # 150 per hour is the normal Fitbit rate limit, but we do two requests
    rate_limit = (150.0 / 2) / (60 * 60)

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.fitbit.com'
        self.uri = '/1/user/-/activities/date/%Y-%m-%d.json'
        self.steps_uri = '/1/user/-/activities/steps/date/%Y-%m-%d/1d.json'
        self.refresh_token_uri = '/oauth2/token'

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']
        self._REFRESH_TOKEN = self.config['oauth2_refresh_token']

        self._ENCODED_USER_ID = self.config['encoded_user_id']
        self._SIGNUP_DATE = self.config['signup_date']
        self._EMBED_INTRADAY_STEPS = self.config.get(
            'embed_intraday_steps', True
        )

        # convert SIGNUP_DATE to naive UTC datetime
        self.signup_date = self.timezone.localize(
            datetime.datetime.strptime(self._SIGNUP_DATE, "%Y-%m-%d")
        ).astimezone(pytz.utc).replace(tzinfo=None)

        self.next_date = None

        self._headers = {
            'Authorization': 'Bearer %s' % (self._ACCESS_TOKEN)
        }
        self._last_status = None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.text = Fitbit.get_text(raw)
        e.occurred = datetime.datetime.strptime(
            raw['datetime'], '%a %b %d %H:%M:%S +0000 %Y'
        )
        e.raw = raw

        return e

    def refresh_access_token(self):
        h = httplib2.Http()

        body = {
            "grant_type": "refresh_token",
            "refresh_token": self._REFRESH_TOKEN
        }

        # make refresh request, update config
        resp, content = h.request(
            self.url + self.refresh_token_uri,
            "POST",
            urllib.parse.urlencode(body),
            headers={
                'Authorization': 'Basic ' + base64.b64encode(
                    str.encode(self._CLIENT_ID + ":" + self._CLIENT_SECRET)
                ).decode('utf-8'),
                'Content-type': 'application/x-www-form-urlencoded'
            }
        )

        if resp.status != 200:
            raise HTTPRequestFailure(
                "received non-200 status %s while refreshing tokens:\n%s" % (
                    str(resp.status),
                    content
                )
            )

        data = json.loads(content.decode('utf-8'))

        self._ACCESS_TOKEN = data["access_token"]
        self.config['oauth2_access_token'] = self._ACCESS_TOKEN
        self.overrides['oauth2_access_token'] = self._ACCESS_TOKEN

        self._REFRESH_TOKEN = data["refresh_token"]
        self.config['oauth2_refresh_token'] = self._REFRESH_TOKEN
        self.overrides['oauth2_refresh_token'] = self._REFRESH_TOKEN

        self._headers = {
            'Authorization': 'Bearer %s' % (self._ACCESS_TOKEN)
        }

    def parse_status(self, resp, content, url, headers):
        # response status of 401 indicates we need to refresh our token
        if resp.status == 401:

            # prevent infinite loop of attempting to refresh token if something
            # goes wrong
            if self._last_status == 401:
                raise RefreshTokenFailure(
                    "Received 401 response after attempt to refresh tokens."
                )

            self._last_status = 401
            self.refresh_access_token()

            # this update must always occur even in dry-run mode or any
            # subsequent API requests will fail
            self.store.update_feeds([self])

            return True, url, self._headers
        else:
            self._last_status = resp.status

        return Feed.parse_status(self, resp, content, url, headers)

    def fetch_intraday_steps(self, data):
        h = httplib2.Http()

        # convert nextdate to our local timezone
        nextdate_local = self.timezone.normalize(
            self.next_date.astimezone(self.timezone)
        )

        # create request
        uri = nextdate_local.strftime(self.steps_uri)

        url = self.url + uri

        success = False

        while not success:
            resp, content = h.request(url, "GET", headers=self._headers)

            # retry request if required (using the same url and headers)
            retry, _, _ = self.parse_status(resp, content, url, self._headers)

            success = not retry

        steps_data = json.loads(content.decode('utf-8'))

        # prune the 0 steps minutes out
        steps_data['activities-steps-intraday']['dataset'] = list(
            filter(
                lambda x: x['value'] != 0,
                steps_data['activities-steps-intraday']['dataset']
            )
        )

        data.update(steps_data)

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

        return request_url, self._headers

    def init_parse_params(self, **kwargs):

        # next request is last_updated + 1
        last_updated = kwargs.get('last_updated', self.signup_date)

        self.next_date = last_updated + datetime.timedelta(days=1)
        self.next_date = pytz.utc.localize(self.next_date)

        if not _should_make_request(self.next_date):
            return None, None

        return self._make_request()

    def parse(self, data):

        # before we update self.next_date, add the intraday data
        if self._EMBED_INTRADAY_STEPS:
            self.fetch_intraday_steps(data)

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
