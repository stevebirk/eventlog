import sys
import re
import copy
import difflib

from flask import request, current_app
from flask.signals import got_request_exception

from werkzeug.exceptions import HTTPException

from flask_restful import Api as _Api
from flask_restful import abort
from flask_restful.reqparse import Argument as _Argument
from flask_restful.utils import http_status_message, cors

envelope = {
    "meta": {
        "code": None
    },
    "data": {},
}

error_meta = {
    "meta": {
        "error_type": "Unknown",
        "error_message": ""
    }
}

pagination = {
    "pagination": {}
}


class Api(_Api):

    def handle_error(self, e):
        """Error handler for the API transforms a raised exception into a
        Flask response, with the appropriate HTTP status code and body.

        :param e: the raised Exception object
        :type e: Exception

        """
        got_request_exception.send(
            current_app._get_current_object(), exception=e
        )

        is_http_exception = isinstance(e, HTTPException)

        if not is_http_exception and current_app.propagate_exceptions:
            exc_type, exc_value, tb = sys.exc_info()
            if exc_value is e:
                raise
            else:  # pragma: no cover
                raise e

        if is_http_exception:
            code = e.code
            default_data = {
                'message': getattr(e, 'description', http_status_message(code))
            }
        else:
            code = 500
            default_data = {
                'message': http_status_message(code),
            }

        data = getattr(e, 'data', default_data)
        headers = {
            'Access-Control-Allow-Origin': '*'
        }

        if code >= 500:
            exc_info = sys.exc_info()

            if exc_info[1] is None:  # pragma: no cover
                exc_info = None

            current_app.log_exception(exc_info)

        help_on_404 = current_app.config.get("ERROR_404_HELP", True)
        if code == 404 and help_on_404:
            rules = dict(
                [
                    (re.sub('(<.*>)', '', rule.rule), rule.rule)
                    for rule in current_app.url_map.iter_rules()
                ]
            )

            close_matches = difflib.get_close_matches(
                request.path, rules.keys()
            )

            if close_matches:
                # If we already have a message, add punctuation and
                # continue it.
                if "message" in data:
                    data["message"] = data["message"].rstrip('.') + '. '
                else:  # pragma: no cover
                    data["message"] = ""

                data['message'] += (
                    'You have requested this URI [' + request.path +
                    '] but did you mean ' +
                    ' or '.join((rules[match] for match in close_matches)) +
                    ' ?'
                )

        if code == 405:
            headers['Allow'] = e.valid_methods

        enhanced_data = copy.deepcopy(envelope)
        enhanced_data.update(copy.deepcopy(error_meta))
        enhanced_data["meta"]["error_type"] = e.__class__.__name__
        enhanced_data["meta"]["code"] = code
        enhanced_data["meta"]["error_message"] = data['message']

        resp = self.make_response(enhanced_data, code, headers)

        if code == 401:  # pragma: no cover
            resp = self.unauthorized(resp)

        return resp


class Argument(_Argument):

    def convert(self, value, op):
        try:
            return super().convert(value, op)
        except Exception as e:
            message = "Invalid value for '%s': %s" % (self.name, str(e))
            raise type(e)(message)

    def handle_validation_error(self, error, bundle_errors):
        abort(400, message=str(error))


api = Api(catch_all_404s=True, decorators=[cors.crossdomain(origin='*')])
