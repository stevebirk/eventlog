import datetime
import random
import string
import uuid
import simplejson as json

# commonly used test methods

from eventlog.lib.events import DATEFMT
from eventlog.lib.util import pg_strptime

random.seed(12)


def db_drop_all_data(conn):
    """drop all test data"""

    prev = conn.autocommit
    conn.autocommit = False

    try:
        cur = conn.cursor()
        cur.execute('drop table related_events;')
        cur.execute('drop table events;')
        cur.execute('drop table feeds;')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    except psycopg2.Error:
        conn.rollback()
        raise

    conn.autocommit = prev


def db_init_schema(conn, schemafile):
    """setup database schema"""

    statements = open(schemafile).read()

    prev = conn.autocommit
    conn.autocommit = False

    try:
        cur = conn.cursor()
        cur.execute(statements)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    except psycopg2.Error:
        conn.rollback()
        raise

    conn.autocommit = prev


def db_insert_feeds(conn, feeds):
    """insert provided data into feeds table"""

    prev = conn.autocommit
    conn.autocommit = False

    try:
        cur = conn.cursor()

        for f in feeds:
            fields = sorted(f.keys())
            values = [f[field] for field in fields]

            q = "insert into feeds (%s) values (%s)" % (
                ', '.join(fields),
                ', '.join(['%s']*len(fields))
            )

            cur.execute(q, values)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    except psycopg2.Error:
        conn.rollback()
        raise

    conn.autocommit = prev


def db_drop_all_events(conn):
    prev = conn.autocommit
    conn.autocommit = False

    try:
        cur = conn.cursor()
        cur.execute("truncate table events cascade;")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    except psycopg2.Error:
        conn.rollback()
        raise

    conn.autocommit = prev


def feeds_create_fake(num, modulename):
    return {
        'id': num,
        'full_name': 'Test Feed %d' % num,
        'short_name': 'testfeed%d' % num,
        'favicon': 'img/source/testfeed%d.png' % num,
        'color': '%06x' % (num % 1048576),
        'module': modulename + '.testfeed%d' % num,
        'config': {'configkey%d' % i: 'configval%d' % i for i in range(5)},
        'is_public': bool(not (num % 10 == 0)),  # 0, 10, 20
        'is_updating': bool(num % 2),  # 1, 3, 5, ... 23
        'is_searchable': bool(num % 3 == 0)  # 0, 3, 6, 9, 12
    }


def events_create_fake(distribution, start, end):
    total = sum([i[1] for i in distribution])

    events = []

    delta = (end - start) / total
    occurred = start

    for feed_json, num in distribution:
        feed = json.loads(feed_json)

        for i in range(num):

            num_related = random.randint(0, 10) if feed['id'] in [7, 18] else 0

            events.append(
                events_create_single(
                    feed,
                    occurred,
                    has_original=(feed['id'] % 10),
                    has_raw=(feed['id'] != 15),
                    has_archived=(feed['id'] % 12),
                    has_thumbnail=(feed['id'] % 2),
                    num_related=num_related,
                    text=(feed['id'] % 6),
                    title=(feed['id'] % 2)
                )
            )

            occurred += delta

    return events


def events_create_single(feed, occurred, has_original=False, has_raw=True,
                         has_archived=False, has_thumbnail=False,
                         num_related=0, text=False, title=True):

    occurred_str = occurred.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    if occurred.microsecond == 0:
        occurred_str = occurred.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    d = {
        'id': str(uuid.uuid4()),
        'title': str(random_string(10)) if title else None,
        'text': str(random_string(20)) if text else None,
        'link': str(random_string(20)),
        'occurred': occurred_str,
        'feed': {
            'id': feed['id'],
            'full_name': str(feed['full_name']),
            'short_name': str(feed['short_name']),
            'favicon': str(feed['favicon']),
            'color': str(feed['color'])
        },
        'raw': None,
        'thumbnail': None,
        'original': None,
        'archived': None,
        'related': None
    }

    if has_original:
        path = 'original/' + d['id'][-2:] + '/' + d['id'] + '_orig.png'
        d['original'] = {
            'path': path,
            'size': {
                'height': random.randint(200, 10000),
                'width': random.randint(200, 10000)
            }
        }

    if has_raw:
        d['raw'] = random_dict(feed['short_name'])

    if has_archived:
        path = 'archive/' + d['id'] + '/' + feed['short_name'] + '.html'
        d['archived'] = {
            'path': path
        }

    if has_thumbnail:
        path = 'thumbnail/' + d['id'][:2] + '/' + d['id'] + '_thumb.png'
        d['thumbnail'] = {
            'path': path,
            'size': {
                'height': 200,
                'width': 200
            }
        }

    if num_related > 0:
        d['related'] = []
        for i in range(num_related):
            related_occurred = (
                occurred + (i + 1) * datetime.timedelta(minutes=3)
            )

            d['related'].append(
                events_create_single(
                    feed,
                    related_occurred,
                    has_original=has_original,
                    has_raw=has_raw,
                    has_archived=has_archived,
                    has_thumbnail=has_thumbnail
                )
            )

    return d


def events_compare(testcase, orig, new):
    # need to modify date format behaviour
    # i.e. orig has PostGres format, new.dict will have nicer format
    for d in orig:
        d['occurred'] = pg_strptime(d['occurred']).strftime(DATEFMT)

        if d['related'] is not None:
            for r in d['related']:
                r['occurred'] = pg_strptime(r['occurred']).strftime(DATEFMT)
                r['feed'] = None

    old_max_diff = testcase.maxDiff
    testcase.maxDiff = None

    for i in range(len(orig)):
        testcase.assertDictEqual(orig[i], new[i].dict())

    testcase.maxDiff = old_max_diff


def random_string(length):
    return ''.join(
        random.sample((string.ascii_letters + "012345689") * 2, length)
    )


def random_dict(base, leaf=False):
    d = {}

    for l in base[:5]:
        key = l + random_string(random.randint(3, 10))
        key = str(key)

        if l == 'e' and not leaf:
            d[key] = random_dict(key, leaf=True)
        elif l == 'j' and not leaf:
            d[key] = []
            for i in range(random.randint(1, 5)):
                d[key].append(random_dict(key, leaf=True))
        else:
            d[key] = random_val()

    return d


def random_val():
    my_int = random.randint(1, 10)
    return random.choice(
        [None, "foo", "bar", "jazz123", my_int]
    )


def index_check_documents(testcase, store, from_store, should_exist=True):
    # force merge of whoosh to avoid phantom documents
    store._index._index.optimize()

    with store._index._index.searcher() as searcher:
        documents = list(searcher.documents())

        events_by_id = {}
        for e in from_store:
            events_by_id[e.id] = e

            if e.related is not None:
                for r in e.related:
                    events_by_id[r.id] = r

        if should_exist:
            testcase.assertEqual(len(documents), len(events_by_id))

        for doc in documents:
            if should_exist:
                testcase.assertIn(doc['id'], events_by_id)
            else:
                testcase.assertNotIn(doc['id'], events_by_id)


def to_pg_datetime_str(data, field):
    data[field] = data[field].replace(' ', 'T')
    data[field] += '+00:00'


if __name__ == "__main__":
    import time
    import feed_generator
    from eventlog.lib.events import Event

    feeds = [
        feeds_create_fake(i, 'feed_generator')
        for i in range(feed_generator.MAX_NUM)
    ]

    s = time.time()

    # add our events
    distribution = [(json.dumps(feed), 100) for feed in feeds]

    event_dicts = events_create_fake(
        distribution,
        datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        datetime.datetime(2013, 3, 24, 0, 0, 0, 0)
    )
    e = time.time()
    print(len(event_dicts), (e - s) / len(event_dicts))
    print(e - s)
