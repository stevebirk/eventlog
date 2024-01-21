import copy
import datetime

from flask import current_app, url_for
from flask_restful import reqparse, abort, Resource

from eventlog.service.core.store import store
from eventlog.service.core.api import api, envelope, pagination, Argument
from eventlog.service.core.auth import is_authorized
from eventlog.service.core.caching import cache, make_cache_key
from eventlog.service.core.inputs import (limit, comma_separated, tz,
                                          datetime_format, date_format,
                                          DATETIME_FMT, DATE_FMT)

import eventlog.service.core.cursor

from eventlog.lib.store.pagination import InvalidPage


def to_query_params(args, cursor):
    params = {}

    # process dates and datetime args first
    if args.on:
        params["on"] = args.on.strftime(DATE_FMT)

    if args.before:
        params["before"] = args.before.strftime(DATETIME_FMT)

    if args.after:
        params["after"] = args.after.strftime(DATETIME_FMT)

    params["cursor"] = eventlog.service.core.cursor.serialize(cursor)

    remaining = [(k, v) for k, v in args.items() if k not in params]

    # convert arguments back into query parameters
    for name, value in remaining:
        if isinstance(value, list):
            params[name] = ','.join(value)
        elif value is not None:
            params[name] = str(value)

    querystring = ''

    if params:
        querystring = '?'
        querystring += '&'.join(["%s=%s" % (k, v) for k, v in params.items()])

    return querystring


@api.resource('/events/<string:event_id>')
class Events(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser(argument_class=Argument)
        self.parser.add_argument(
            'tz',
            type=tz,
            help='specify timezone as IANA info key for date values',
            location='args'
        )

        super().__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self, event_id):
        args = self.parser.parse_args()

        es = store.get_events_by_ids([event_id], timezone=args.tz)

        is_public = True if not is_authorized() else None

        accessible_feeds = store.get_feeds(is_public=is_public)

        found = list(es)

        if found:
            e = found[0]
        else:
            e = None

        if e is None or e.feed['short_name'] not in accessible_feeds:
            abort(404, message="No event with ID: '%s'" % (event_id))

        data = copy.deepcopy(envelope)
        data['meta']['code'] = 200
        data['data'] = e.dict(base_uri=current_app.config['STATIC_URL'])

        return data


@api.resource('/events')
class EventsList(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser(argument_class=Argument)

        self.parser.add_argument(
            'limit',
            type=limit,
            help='number of events to retrieve',
            default=current_app.config['PAGE_SIZE_DEFAULT'],
            location='args'
        )
        self.parser.add_argument(
            'feeds',
            type=comma_separated,
            help='filter events by specific feed(s)',
            location='args'
        )
        self.parser.add_argument(
            'q',
            type=str,
            help='filter events by search query',
            location='args'
        )
        self.parser.add_argument(
            'embed_related',
            choices=['full', 'count', False],
            help=('specify whether to embed related events data '
                  '(ignored for search queries), can specify full '
                  'embed, or just counts (default=full)'),
            default='full',
            location='args'
        )
        self.parser.add_argument(
            'tz',
            type=tz,
            help='specify timezone as IANA info key for datetime values',
            location='args'
        )
        self.parser.add_argument(
            'on',
            type=date_format,
            help='filter events by occurred date',
            location='args'
        )
        self.parser.add_argument(
            'before',
            type=datetime_format,
            help='filter events that occurred before datetime',
            location='args'
        )
        self.parser.add_argument(
            'after',
            type=datetime_format,
            help='filter events that occurred after datetime',
            location='args'
        )
        self.parser.add_argument(
            'cursor',
            type=str,
            help='pagination cursor',
            location='args'
        )

        super().__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self):
        args = self.parser.parse_args()

        if args.cursor:
            try:
                args.cursor = eventlog.service.core.cursor.parse(
                    args.cursor,
                    args.tz
                )
            except ValueError as e:
                abort(400, message="Invalid value for 'cursor': " + str(e))

        all_feeds = store.get_feeds()

        feeds = all_feeds

        if not is_authorized():
            feeds = [k for k, f in all_feeds.items() if f.is_public]

        embed_related = False if not args.embed_related else True

        if args.feeds:
            invalid_feeds = set(args.feeds) - set(feeds)

            if invalid_feeds:
                abort(
                    400,
                    message="Invalid value(s) for 'feed': %s" % (
                        ', '.join(invalid_feeds)
                    )
                )

            feeds = args.feeds

        if args.after and args.before:  # validate timerange
            if args.after >= args.before:
                abort(
                    400,
                    message="Invalid timerange: 'after' must be < 'before'"
                )

        if args.q:  # fetch by search query
            everything = set(all_feeds)
            requested = set(feeds)
            unsearchable = set(
                [k for k, f in all_feeds.items() if not f.is_searchable]
            )

            # mask feeds not requested or unsearchable
            to_mask = (everything - requested).union(unsearchable)
            to_mask = sorted(to_mask)

            # filter requested feeds that are searchable
            to_filter = requested - unsearchable
            to_filter = sorted(to_filter)

            # optimization: use the smaller subset
            if len(to_mask) > len(to_filter):
                to_mask = None
            else:
                to_filter = None

            es = store.get_events_by_search(
                args.q,
                before=args.before,
                after=args.after,
                to_mask=to_mask,
                to_filter=to_filter,
                pagesize=args.limit,
                timezone=args.tz
            )

            # freeze search, so subsequent pages don't change even if new data
            # is added
            if es.latest is not None:
                args.before = es.latest + datetime.timedelta(microseconds=1)

        elif args.on:
            es = store.get_events_by_date(
                args.on,
                feeds=feeds,
                embed_related=embed_related,
                pagesize=args.limit,
                timezone=args.tz
            )
        else:  # fetch
            es = store.get_events_by_timerange(
                after=args.after,
                before=args.before,
                feeds=feeds,
                pagesize=args.limit,
                embed_related=embed_related,
                timezone=args.tz
            )

        try:
            p = es.page(cursor=args.cursor)
        except InvalidPage:
            abort(
                400,
                message=(
                    "Invalid value for 'cursor': value range is 0 < page <= %d"
                ) % (es.num_pages)
            )

        data = copy.deepcopy(envelope)
        data['meta']['code'] = 200
        data.update(copy.deepcopy(pagination))

        related_count_only = True if (args.embed_related == 'count') else False

        data['data'] = [
            e.dict(
                base_uri=current_app.config['STATIC_URL'],
                related_count_only=related_count_only
            )
            for e in p
        ]

        if p.next is not None:
            querystring = to_query_params(args, p.next)
            data['pagination']['next'] = url_for(self.endpoint) + querystring

        return data
