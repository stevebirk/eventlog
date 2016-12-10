#!/usr/bin/env python

"""
(Re-)Download thumbnail image data.

Usage: thumbnails.py [-hj] [--redownload] [--only-for=<feed>]

-h, --help              Show this screen.
-j, --dry-run           Enable dry run mode, i.e. no thumbnail images saved.
    --redownload        Re-download only for events with existing thumbnails
    --only-for=<feed>   Only perform actions for specified feed.
"""

import os
import sys
import time
import logging
import docopt

from flask import Flask

from eventlog.lib.store import Store
from eventlog.lib.events import UnableToRetrieveImageException

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

    only_for = [args['--only-for']] if args['--only-for'] is not None else None

    # get events
    es = store.get_events_by_timerange(flattened=True, feeds=only_for)

    batch = []

    for e in es:
        if e.thumbnail is not None and not args['--redownload']:
            continue

        if e.thumbnail is None and args['--redownload']:
            continue

        f = feeds[e.feed['short_name']]

        try:
            thumbnail_url = f.to_event(e.raw).thumbnail_url
        except Exception:
            continue

        if thumbnail_url is not None:
            logging.info(
                'need to download url=%s, feed=%s, id=%s',
                thumbnail_url,
                e.feed['short_name'],
                e.id
            )

            e.thumbnail_url = thumbnail_url

            try:
                e.add_thumbnail(
                    f.config['thumbnail_width'],
                    f.config['thumbnail_height'],
                    f.config['media_dir'],
                    f.config['thumbnail_subdir'],
                    dry=args["--dry-run"]
                )

                if e.thumbnail is not None:
                    batch.append(e)

            except UnableToRetrieveImageException:
                logging.warning(
                    'download failed url=%s, feed=%s, id=%s',
                    thumbnail_url,
                    e.feed['short_name'],
                    e.id
                )

        if len(batch) == BATCH_LEN:
            logging.info('updating batch of %d events', BATCH_LEN)
            store.update_events(batch, dry=args["--dry-run"])
            batch = []

    if batch:
        logging.info('updating batch of %d events', len(batch))
        store.update_events(batch, dry=args["--dry-run"])

    end = time.time()

    logging.info('downloading thumbnails took %.3fs', end - start)
