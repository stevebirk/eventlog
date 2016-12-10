import unittest
import os.path
import shutil
import pkg_resources

import psycopg2

from flask import Flask

from eventlog.lib.store import Store

from ..util import db_drop_all_data, db_init_schema, db_drop_all_events
from ..util import db_insert_feeds, feeds_create_fake

from .. import feed_generator

SCHEMA_PATH = pkg_resources.resource_filename(
    'eventlog.lib', 'store/sql/eventlog.sql'
)

app = Flask(__name__)
store = Store()


class TestStoreWithDBBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.maxDiff = None

        cls._config = {
            'DB_USER': 'test',
            'DB_PASS': 'test',
            'DB_NAME': 'test',
            'INDEX_DIR': '../testindex',
            'TIME_ZONE': 'America/Toronto'
        }

        # create connection
        cls._conn = psycopg2.connect(
            database=cls._config['DB_NAME'],
            user=cls._config['DB_USER'],
            password=cls._config['DB_PASS']
        )

        # create test feeds
        cls._feeds = [
            feeds_create_fake(i, 'lib.feed_generator')
            for i in range(feed_generator.MAX_NUM)
        ]

        # prep database
        db_drop_all_data(cls._conn)
        db_init_schema(cls._conn, SCHEMA_PATH)

        # prep database data
        db_insert_feeds(cls._conn, cls._feeds)

        # remove any existing index
        if os.path.exists(cls._config['INDEX_DIR']):
            shutil.rmtree(cls._config['INDEX_DIR'])

        # init our store
        app.config['STORE'] = cls._config
        store.init_app(app)

    @classmethod
    def tearDownClass(cls):
        # remove any existing index
        if os.path.exists(cls._config['INDEX_DIR']):
            shutil.rmtree(cls._config['INDEX_DIR'])
