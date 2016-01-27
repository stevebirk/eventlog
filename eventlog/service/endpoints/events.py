import copy

from flask import current_app, url_for
from flask.ext.restful import reqparse, abort, Resource
from flask.ext.restful.inputs import boolean

from eventlog.service.core.store import store
from eventlog.service.core.api import api, envelope, pagination, Argument
from eventlog.service.core.auth import is_authorized
from eventlog.service.core.caching import cache, make_cache_key
from eventlog.service.core.inputs import (limit, comma_separated, tz,
                                          datetime_format, date_format)


def args_to_query_params(args):

    params = []

    for name, value in args.items():
        if isinstance(value, list):
            params.append('%s=%s' % (name, ','.join(value)))
        elif value is not None:
            params.append('%s=%s' % (name, str(value)))

    querystring = ''
    if len(params):
        querystring = '?' + '&'.join(params)

    return querystring


@api.resource('/events/<string:event_id>')
class Events(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser(argument_class=Argument)
        self.parser.add_argument(
            'tz',
            type=tz,
            help='specify timezone as IANA info key for date values'
        )

        super(Events, self).__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self, event_id):
        args = self.parser.parse_args()

        es = store.get_events_by_ids(
            [event_id],
            timezone=args.tz
        )

        is_public = True if not is_authorized() else None

        accessible_feeds = store.get_feeds(is_public=is_public)

        if es.count == 1:
            e = list(es)[0]
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
            'page',
            type=int,
            help='page number to retrieve',
            default=1
        )
        self.parser.add_argument(
            'limit',
            type=limit,
            help='number of events to retrieve',
            default=current_app.config['PAGE_SIZE_DEFAULT']
        )
        self.parser.add_argument(
            'feeds',
            type=comma_separated,
            help='retrieve events by specific feed(s)'
        )
        self.parser.add_argument(
            'q',
            type=str,
            help='retrieve events by search query'
        )
        self.parser.add_argument(
            'embed_related',
            choices=['full', 'count', False],
            help=('specify whether to embed related events data '
                  '(ignored for search queries), can specify full '
                  'embed, or just counts (default=full)'),
            default='full'
        )
        self.parser.add_argument(
            'tz',
            type=tz,
            help='specify timezone as IANA info key for date values'
        )
        self.parser.add_argument(
            'on',
            type=date_format,
            help='retrive events that occurred on date'
        )
        self.parser.add_argument(
            'before',
            type=datetime_format,
            help='retrieve events that occurred prior to date'
        )
        self.parser.add_argument(
            'after',
            type=datetime_format,
            help='retrieve events that occurred after date'
        )

        super(EventsList, self).__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self):
        args = self.parser.parse_args()

        is_public = True if not is_authorized() else None

        accessible_feeds = store.get_feeds(is_public=is_public)

        embed_related = False if not args.embed_related else True

        if args.feeds:
            invalid_feeds = set(args.feeds) - set(accessible_feeds)

            if invalid_feeds:
                abort(
                    400,
                    message="Unrecognized feed(s): %s" % (
                        ', '.join(invalid_feeds)
                    )
                )

            feeds = args.feeds
        else:
            feeds = accessible_feeds

        if args.q:  # fetch by search query
            # all feeds
            to_mask = set(store.get_feeds())

            # remove feeds requested
            to_mask -= set(feeds)

            # add back unsearchable
            to_mask = to_mask.union(set(store.get_feeds(is_searchable=False)))
            to_mask = sorted(to_mask)

            to_filter = set(feeds)

            # remove unsearchable feeds
            to_filter -= set(store.get_feeds(is_searchable=False))
            to_filter = list(to_filter)

            # optimization: use the smaller subset
            if len(to_mask) > len(to_filter):
                to_mask = None
            else:
                to_filter = None

            es = store.get_events_by_search(
                args.q,
                to_mask=to_mask,
                to_filter=to_filter,
                pagesize=args.limit,
                timezone=args.tz
            )
        elif args.on:
            es = store.get_events_by_date(
                args.on,
                feeds=feeds,
                embed_related=embed_related,
                pagesize=args.limit,
                timezone=args.tz
            )
        elif args.after and args.before:  # fetch by timerange
            if args.after >= args.before:
                abort(
                    400,
                    message="Invalid timerange, after must be < before"
                )

            es = store.get_events_by_timerange(
                start=args.after,
                end=args.before,
                feeds=feeds,
                pagesize=args.limit,
                embed_related=embed_related,
                timezone=args.tz
            )
        elif args.after:  # fetch by timerange
            es = store.get_events_by_timerange(
                start=args.after,
                feeds=feeds,
                pagesize=args.limit,
                embed_related=embed_related,
                timezone=args.tz
            )
        elif args.before:  # fetch by timerange
            es = store.get_events_by_timerange(
                end=args.before,
                feeds=feeds,
                pagesize=args.limit,
                embed_related=embed_related,
                timezone=args.tz
            )
        else:  # fetch standard
            es = store.get_events(
                feeds=feeds,
                pagesize=args.limit,
                embed_related=embed_related,
                timezone=args.tz
            )

        # fetch requested page
        p = es.get_page(args.page)

        if p is None:
            abort(
                400,
                message=(
                    "Invalid value for 'page': "
                    "value range is 0 < page <= %d"
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
            for e in p.events
        ]

        if p.next is not None:
            args.page = p.next
            querystring = args_to_query_params(args)
            data['pagination']['next'] = url_for(self.endpoint) + querystring

        if p.prev is not None:
            args.page = p.prev
            querystring = args_to_query_params(args)
            data['pagination']['prev'] = url_for(self.endpoint) + querystring

        return data
