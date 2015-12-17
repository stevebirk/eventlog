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

Installation
------------

Recommended installation is in a `virtualenv` using pip or manual use of
the `setup.py` file:

    python setup.py install

A PostgreSQL (>= 9.5) database and user should be created for this application
and the schema in `eventlog/lib/store/sql/eventlog.sql` applied to it.

PostgreSQL must have it's timezone set to UTC for datetime storage to work
correctly. This is done by settings `timezone = 'UTC'` in your
`postgresql.conf` file.

Configuration
-------------

### General

Application configuration is expected to be present in file indicated via the
environment variable `EVENTLOG_SETTINGS`.

i.e.

    EVENTLOG_SETTINGS=/path/to/settings.conf

The default location of this file is:

    <sys.prefix>/etc/eventlog/eventlog.conf

Installation creates a `<sys.prefix>/etc/eventlog/eventlog.conf.sample` file
which documents the available configuration parameters.

### Feeds

Feed configuration consists of rows in the `feeds` table with the following
columns:

    full_name     - full name of feed (can contain spaces, etc)
    short_name    - short name of feed (only alphanumeric characters)
    favicon       - path within MEDIA_DIR where favicon for feed is stored
    color         - 6-character HEX code for colour associated with feed
    module        - module name for feed (i.e. eventlog.ext.feeds.lastfm)
    config        - any module specific config in JSON form (see below)
    is_public     - flag indicated feed is publically visible
    is_updating   - flag indicated feed should be updated
    is_searchable - flag indicated feed is searchable

### Feed Specific

Most feeds require their own configuration to specify usernames, OAuth
credentials, etc. This configuration is stored in JSON form in the
correspoding row of the `feeds` database table.

The expected configuration parameters for the built-in feeds are documented
below:

**Behance**

    username                # Behance username
    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token

**Delicious**

    username                # Delicious username

**Dribbble**

    username                # Dribbble username
    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token

**Fitbit**

    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token
    encoded_user_id         # Encoded Fitbit user ID (see Fitbit API docs)
    signup_date             # date Fitbit account was created in YYYY-MM-DD
                            # form

**Flickr**

    oauth1_consumer_key     # OAuth1 consumer key
    oauth1_consumer_secret  # OAuth1 consumer secret
    oauth1_user_key         # OAuth1 user key
    oauth1_user_secret      # Oauth1 user secret

**Foursquare**

    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token

**Instagram**

    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token

**Last.FM**

    username                # Last.FM username
    api_key                 # API key
    num_limit               # limit of how many recent tracks to request at a
                            # time (i.e. 50)

**Reddit**

    username                # Reddit username
    feed_key                # feed key

**Runkeeper**

    oauth2_client_id        # OAuth2 client ID
    oauth2_client_secret    # OAuth2 client secret
    oauth2_access_token     # OAuth2 access token

**Twitter**

    oauth1_consumer_key     # OAuth1 consumer key
    oauth1_consumer_secret  # OAuth1 consumer secret
    oauth1_user_key         # OAuth1 user key
    oauth1_user_secret      # Oauth1 user secret

Setup
-----

### Data Updating

Data updating involves running a script which will process any new events on
the configured list of feeds.

The current suggested method for doing this is using `cron` with the following
entry in the crontab:

    */10  *  *  *  *  EVENTLOG_SETTINGS=<settings module> <path/to/updater.py>

This will run the updater script every 10 minutes.

NOTE: the `EVENTLOG_SETTINGS` environment variable is only necessary if using
      a non-standard configuration file location

### API Service

The HTTP/JSON API service is a standard Python WSGI application and can be
served up using any of the various methods for serving such an application.

The suggested setup is to use something like `uwsgi` for the application itself
and `nginx` or another webserver for the static media content.

Adding New Services
-------------------

Adding a new service requires creating an appropriate class inheriting from
`eventlog.lib.feeds.Feed`, and overloading the appropriate methods. Please see
existing feeds in `eventlog.ext.feeds` for examples of how to do so.

This class should be placed in a module accessible on the `PYTHONPATH`, and
configured appropriately as described above.

Tests
-----

The `eventlog.lib` and `eventlog.service` modules both currently have tests,
with 100% code coverage.

The tests require the `pytest` and `pytest-cov` modules to be installed.

To run the tests, you will need a PostgreSQL instance with a `test` user who
is the owner of a `test` db with password `test`.

With this database available the tests can be run individually, or all
together.

    make test-lib       # test eventlog.lib only
    make test-service   # test eventlog.service only

    make test           # test all
