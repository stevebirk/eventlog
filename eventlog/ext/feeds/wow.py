import httplib2
import json
import datetime
import pprint

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event, Fields

EPIC = 4


class WoW(Feed):

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        base = "http://us.battle.net/api/wow/character/"

        self.url = base + "%s/%s?fields=feed" % (
            self.config['char_realm'],
            self.config['char_name']
        )
        self.item_data_url = "http://us.battle.net/api/wow/item/"
        self.ilevel_threshold = self.config['ilevel_limit']

        self.last_updated = None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = "[" + raw["name"] + "]"
        e.text = "Obtained"
        e.link = "http://www.wowhead.com/item=" + str(raw['id'])
        e.occurred = WoW.parse_date(raw['timestamp'])
        e.raw = raw

        return e

    def verify_entries(self, entries):

        verified = []

        h = httplib2.Http()

        for entry in entries:

            date = WoW.parse_date(entry['timestamp'])
            if self.last_updated is not None and date < self.last_updated:
                continue

            item_data_url = self.item_data_url + str(entry['itemId'])
            resp, content = h.request(item_data_url, "GET")

            if resp.status != 200:
                raise HTTPRequestFailure(
                    "received non-200 status %s for item url '%s':\n%s" % (
                        str(resp.status),
                        item_data_url,
                        content
                    )
                )

            item_data = json.loads(content)

            quality = item_data.get('quality', 0)
            ilevel = item_data.get('itemLevel', 0)

            if (quality == EPIC) and (ilevel >= self.ilevel_threshold):
                entry.update(item_data)
                del entry['itemId']
                verified.append(entry)

        return verified

    def init_parse_params(self, **kwargs):

        self.last_updated = kwargs.get('last_updated', None)

        return self.url, None

    def parse(self, data):

        verified = self.verify_entries(
            [entry for entry in data['feed'] if entry['type'] == "LOOT"]
        )

        events = [self.to_event(entry) for entry in verified]

        return events, None, None

    @staticmethod
    def parse_date(datestr):
        occurred = datetime.datetime.utcfromtimestamp(float(datestr) / 1000.0)
        return occurred

    def load(self, loadfile=None, dumpfile=None):
        raise Exception('Not implemented.')
