import datetime
import codecs
import re

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields


class Delicious(Feed):

    key_field = Fields.LINK

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = "http://feeds.del.icio.us/v2/json/%s" % (
            self.config['username']
        )

    def parse(self, data):
        return [self.to_event(entry) for entry in data], None, None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['d']
        e.link = raw['u']
        e.occurred = datetime.datetime.strptime(
            raw['dt'], '%Y-%m-%dT%H:%M:%SZ'
        )
        e.thumbnail_url = raw['u']
        e.archive_url = raw['u']
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, None

    def parse_status(self, resp, content, url, headers):
        retry, retry_url, retry_headers = Feed.parse_status(
            self, resp, content, url, headers
        )

        if resp.get('x-cache') == 'HIT':

            link_header = resp.get('link')

            if link_header is not None:
                m = re.search('<(.*?)>', link_header)

                if m is not None:
                    retry = True
                    retry_url = m.group(1)

        return retry, retry_url, retry_headers

    def load(self, loadfile=None, dumpfile=None):

        if loadfile is None:
            raise Exception(
                'import of delicious data requires HTML dump file.'
            )

        fh = codecs.open(loadfile, "r", "utf-8")

        try:
            events = []

            for line in fh:
                if 'HREF' in line:

                    title = re.search("TAGS=\".*?\">(.*?)</A>", line).group(1)
                    link = re.search("HREF=\"(.*?)\"", line).group(1)
                    tags = re.search("TAGS=\"(.*?)\"", line).group(1)
                    tags = tags.split(',')

                    dt = int(re.search("ADD_DATE=\"(.*?)\"", line).group(1))
                    dt = datetime.datetime.utcfromtimestamp(dt)
                    dt = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                    data = {
                        "a": self.config['username'],
                        "d": str(title),
                        "n": "",
                        "u": str(link),
                        "t": str(tags),
                        "dt": str(dt)
                    }

                    events.append(self.to_event(data))
        finally:
            fh.close()

        return events
