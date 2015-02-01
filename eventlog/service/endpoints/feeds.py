import copy

from flask import current_app

from flask.ext.restful import reqparse, abort, Resource
from flask.ext.restful.inputs import boolean

from eventlog.service.core.store import store
from eventlog.service.core.api import api, envelope, Argument
from eventlog.service.core.auth import is_authorized
from eventlog.service.core.caching import cache, make_cache_key


@api.resource('/feeds/<string:short_name>')
class Feeds(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser(argument_class=Argument)
        self.parser.add_argument(
            'admin',
            type=boolean,
            help='response should include admin data (config, etc)',
            default=False
        )

        super(Feeds, self).__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self, short_name):
        args = self.parser.parse_args()

        data = copy.deepcopy(envelope)

        is_public = True if not is_authorized() else None

        if is_public:
            args.admin = None

        feeds = store.get_feeds(is_public=is_public)

        if short_name not in feeds:
            abort(404, message="Unrecognized feed '%s'" % (short_name))

        data['data'] = feeds[short_name].dict(
            admin=args.admin,
            base_uri=current_app.config['STATIC_URL']
        )
        data['meta']['code'] = 200

        return data


@api.resource('/feeds')
class FeedsList(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser(argument_class=Argument)
        self.parser.add_argument(
            'admin',
            type=boolean,
            help='response should include admin data (config, etc)',
            default=False
        )

        super(FeedsList, self).__init__()

    @cache.cached(key_prefix=make_cache_key)
    def get(self):
        args = self.parser.parse_args()

        data = copy.deepcopy(envelope)

        is_public = True if not is_authorized() else None

        if not is_authorized():
            args.admin = None

        feeds = store.get_feeds(is_public=is_public)
        data['data'] = [
            f.dict(
                admin=args.admin,
                base_uri=current_app.config['STATIC_URL']
            ) for f in feeds.values()
        ]
        data['meta']['code'] = 200

        return data
