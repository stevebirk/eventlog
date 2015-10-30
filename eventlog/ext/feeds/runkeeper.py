import datetime
import json
import httplib2
import pytz

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event, Fields


def format_seconds(val):

    val = round(val)

    hours, remainder = divmod(val, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        formatted = "%d:%02d:%02d" % (hours, minutes, seconds)
    else:
        formatted = "%d:%02d" % (minutes, seconds)

    return formatted


class Runkeeper(Feed):

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.runkeeper.com'
        self.uri = '/fitnessActivities'
        self._accept = "application/vnd.com.runkeeper.FitnessActivityFeed+json"

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']

        self._headers = {
            'Authorization': 'Bearer %s' % (self._ACCESS_TOKEN),
            'Accept': self._accept
        }

        self.last_updated = None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.text = Runkeeper.get_text(raw)
        e.link = raw['activity']
        e.occurred = Runkeeper.get_date(raw, self.timezone)
        e.raw = raw

        return e

    def fetch_activities(self, items):

        activities = []

        h = httplib2.Http()

        for item in items:

            item_date = Runkeeper.get_date(item, self.timezone)

            if self.last_updated is not None and item_date < self.last_updated:
                continue

            activity_url = self.url + item['uri']
            headers = {
                'Authorization': 'Bearer %s' % (self._ACCESS_TOKEN),
                'Accept': 'application/vnd.com.runkeeper.FitnessActivity+json'
            }
            resp, content = h.request(activity_url, "GET", headers=headers)

            if resp.status != 200:
                raise HTTPRequestFailure(
                    "received non-200 status %s for activity url '%s':\n%s" % (
                        str(resp.status),
                        activity_url,
                        content
                    )
                )

            activity = json.loads(content)

            activities.append(activity)

        return activities

    def init_parse_params(self, **kwargs):

        self.last_updated = kwargs.get('last_updated', None)

        return self.url + self.uri, self._headers

    def parse(self, data):

        events = [
            self.to_event(activity)
            for activity in self.fetch_activities(data['items'])
        ]

        next_uri = data.get('next')

        next_url = None
        if next_uri is not None:
            next_url = self.url + next_uri

        return events, next_url, self._headers

    @staticmethod
    def get_text(entry):

        template = ' '.join([
            'Completed a %.2f km %s activity',
            'with a duration of %s',
            'at an average pace of %s per km'
        ])

        distance = entry['total_distance'] / 1000.0
        seconds_per_km = entry['duration'] / distance

        text = template % (
            distance,
            entry['type'].lower(),
            format_seconds(entry['duration']),
            format_seconds(seconds_per_km)
        )

        return text

    @staticmethod
    def get_date(entry, tz):

        naive_dt = datetime.datetime.strptime(
            entry['start_time'], '%a, %d %b %Y %H:%M:%S'
        )

        local_dt = tz.localize(naive_dt)

        utc_dt = pytz.utc.normalize(
            local_dt.astimezone(pytz.utc)
        )

        naive_utc_dt = utc_dt.replace(tzinfo=None)

        return naive_utc_dt
