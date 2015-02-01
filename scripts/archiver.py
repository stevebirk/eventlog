#!/usr/bin/env python

"""
(Re-)Download event archive data.

Usage: archiver.py [-hj]

-h, --help          Show this screen.
-j, --dry-run       Enable dry run mode, i.e. no archives saved.
"""

import os
import sys
import time
import logging
import docopt

from flask import Flask

from eventlog.lib.store import Store
from eventlog.service.util import init_config

BATCH_LEN = 10

store = Store()


def init_logging():
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        ('[%(asctime)s.%(msecs)03d]: '
         '%(levelname)10s | %(name)20s | %(message)s'),
        '%H:%M:%S'
    ))

    l = logging.getLogger()
    l.addHandler(handler)
    l.setLevel(logging.INFO)

if __name__ == "__main__":
    init_logging()

    app = Flask(__name__)
    init_config(app)
    store.init_app(app)

    args = docopt.docopt(__doc__)

    start = time.time()

    feeds = store.get_feeds()

    # get events
    es = store.get_events(flattened=True)

    batch = []

    for e in es:
        if e.archived is not None:
            continue

        f = feeds[e.feed['short_name']]

        try:
            archive_url = f.to_event(e.raw).archive_url
        except Exception:
            continue

        try:
            if archive_url is not None:
                logging.info(
                    'need to archive url=%s, feed=%s, id=%s',
                    archive_url,
                    e.feed['short_name'],
                    e.id
                )

                e.archive_url = archive_url

                e.add_archive(
                    store._config['MEDIA_DIR'],
                    store._config['ARCHIVE_SUBDIR'],
                    dry=args["--dry-run"]
                )

                if e.archived is not None:
                    batch.append(e)

        except Exception:
            logging.exception('unable to download archive')

        if len(batch) == BATCH_LEN:
            logging.info('updating batch of %d events', BATCH_LEN)
            store.update_events(batch, dry=args["--dry-run"])
            batch = []

    if batch:
        logging.info('updating batch of %d events', len(batch))
        store.update_events(batch, dry=args["--dry-run"])

    end = time.time()

    logging.info('downloading archives took %.3fs', end - start)
