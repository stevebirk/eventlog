import sys
import os.path

from setuptools import setup

"""
Eventlog
========

Gather and store events from various web services APIs, and retrieve them
using an HTTP/JSON api which supports full text search.

"""

setup(
    name='Eventlog',
    version='1.0.dev0',
    author='Steve Birk',
    author_email='stevebirk@gmail.com',
    description='storage and HTTP/JSON retrieval API for web service data',
    long_description=__doc__,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application'
    ],
    packages=[
        'eventlog',
        'eventlog.lib',
        'eventlog.lib.store',
        'eventlog.ext',
        'eventlog.ext.feeds',
        'eventlog.service',
        'eventlog.service.core',
        'eventlog.service.endpoints'
    ],
    package_data={'eventlog.lib': ['store/sql/*.sql']},
    data_files=[
        (os.path.join(sys.prefix, 'etc', 'eventlog'),
         ['etc/eventlog.conf.sample'])
    ],
    scripts=[
        'scripts/archiver.py',
        'scripts/cleaner.py',
        'scripts/indexer.py',
        'scripts/originals.py',
        'scripts/thumbnails.py',
        'scripts/updater.py'
    ],
    zip_safe=False,
    install_requires=[
        'Flask>=0.10.1',
        'Flask-Cache>=0.13.1',
        'Flask-RESTful>=0.3.1',
        'Pillow',
        'Whoosh>=2.5',
        'beautifulsoup4',
        'docopt',
        'gevent>=1.0',
        'httplib2',
        'itsdangerous',
        'lxml',
        'oauth2',
        'psycogreen',
        'psycopg2',
        'pytz',
        'simplejson'
    ]
)
