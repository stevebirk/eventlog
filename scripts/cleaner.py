#!/usr/bin/env python

"""
Cleanup any unreferenced media files.

Usage: cleaner.py [-hjvd]

-h, --help          Show this screen.
-j, --dry-run       Enable dry mode, i.e. don't delete anything.
-v, --verbose       Log to stdout instead of file.
-d, --debug         Enable DEBUG level logging. Implies --verbose.
"""

import os
import re
import os.path
import sys
import time
import shutil
import logging
import docopt

from flask import Flask

from eventlog.lib.store import Store
from eventlog.service.util import init_config

store = Store()

IGNORE = ['.DS_Store']


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


def pretty_size(bytes):
    if bytes >= 1073741824:
        return str(bytes / 1024 / 1024 / 1024) + ' GB'
    elif bytes >= 1048576:
        return str(bytes / 1024 / 1024) + ' MB'
    elif bytes >= 1024:
        return str(bytes / 1024) + ' KB'
    elif bytes < 1024:
        return str(bytes) + ' bytes'


def get_size(path):
    total_size = 0

    if os.path.isdir(path):
        # walk
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
    else:
        total_size = os.path.getsize(path)

    return total_size


def get_used_dirs(es):

    paths = {}

    for e in es:
        if e.original is not None:
            paths[e.original['path']] = 1

        if e.thumbnail is not None:
            paths[e.thumbnail['path']] = 1

        if e.archived is not None:
            paths[
                re.match("(.*?-[0-9a-z]{12})", e.archived['path']).group(1)
            ] = 1

    return paths


def remove_media(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def check_media(root, subdir, used, dry=False):

    rootpath = os.path.join(root, subdir)
    checked = 0
    removed = 0
    bytes_removed = 0

    logging.info("checking media in %s", rootpath)

    for hexpair in os.listdir(rootpath):
        if hexpair in IGNORE:
            continue

        # this will be subdirs, i.e. 00, 01, ... , ff
        hexpath = os.path.join(rootpath, hexpair)

        for path in os.listdir(hexpath):
            if path in IGNORE:
                continue

            to_check = str(os.path.join(subdir, hexpair, path.rstrip('/')))
            checked += 1

            if to_check not in used:

                to_remove = str(os.path.join(root, to_check))

                bytes_removed += get_size(to_remove)

                if not dry:
                    logging.info("removing unreferenced %s", to_check)
                    remove_media(to_remove)
                else:
                    logging.info("%s not referenced", to_check)

                removed += 1

    return checked, removed, bytes_removed


if __name__ == "__main__":
    init_logging()

    app = Flask(__name__)
    init_config(app)
    store.init_app(app)

    args = docopt.docopt(__doc__)

    start = time.time()

    # get events
    es = store.get_events(flattened=True)

    # determine on-disk paths that are referrenced
    logging.info("determining used file paths")
    used_paths = get_used_dirs(es)

    # iterate over files
    root = store._config['MEDIA_DIR']
    removed_count = 0
    checked_count = 0
    bytes_removed_total = 0

    subdirs = [
        store._config['THUMBNAIL_SUBDIR'],
        store._config['ORIGINAL_SUBDIR'],
        store._config['ARCHIVE_SUBDIR'],
    ]
    for subdir in subdirs:
        checked, removed, bytes_removed = check_media(
            root, subdir, used_paths, args['--dry-run']
        )
        checked_count += checked
        removed_count += removed
        bytes_removed_total += bytes_removed

    end = time.time()

    logging.info(
        '%d paths checked (%d removed, %s saved) in %.3fs',
        checked_count,
        removed_count,
        pretty_size(bytes_removed_total),
        end - start
    )
