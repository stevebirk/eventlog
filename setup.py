import sys
import os.path

from setuptools import setup

"""
Eventlog
========

Gather and store events and related media from various web service JSON APIs.
Provides a common HTTP/JSON api supporting full text search for retrieving
said data.

Currently includes built-in support for the following services:

* Behance
* Delicious
* Dribbble
* Fitbit
* Flickr
* Foursquare
* Instagram
* Last.FM
* Reddit
* Runkeeper
* Twitter

"""

setup(
    name='Eventlog',
    version='3.0.dev1',
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
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3 :: Only',
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
        'Flask==3.0.0',
        'Flask-Caching>=2.1.0',
        'Flask-RESTful==0.3.10',
        'Pillow',
        'Whoosh>=2.7.4',
        'beautifulsoup4',
        'docopt',
        'gevent>=1.2',
        'httplib2>=0.14.0',
        'itsdangerous',
        'lxml',
        'oauth2',
        'psycogreen',
        'psycopg2',
        'pytz'
    ]
)
