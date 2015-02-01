import copy

from flask.ext.restful import Resource

from eventlog.service.core.api import api, envelope
from eventlog.service.core.auth import generate_auth_token


@api.resource('/token')
class Token(Resource):

    def get(self):
        data = copy.deepcopy(envelope)
        data['data'] = {
            'token': generate_auth_token()
        }
        data['meta']['code'] = 200

        return data
