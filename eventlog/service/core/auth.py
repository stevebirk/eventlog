import string
import random

from flask import current_app, request

from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous import SignatureExpired, BadSignature, BadData


def generate_auth_token():
    s = Serializer(current_app.config['SECRET_KEY'])

    return s.dumps(
        ''.join(random.choice(string.ascii_uppercase) for i in range(12))
    )


def verify_auth_token(token):
    s = Serializer(current_app.config['SECRET_KEY'])

    max_age = current_app.config['AUTH_TOKEN_EXPIRY']
    try:
        data = s.loads(token, max_age=max_age)
    except SignatureExpired:  # pragma: no cover
        return False  # valid token, but expired
    except BadSignature:
        return False  # invalid token
    except BadData:  # pragma: no cover
        return False
    except Exception:  # pragma: no cover
        return False

    return True


def is_authorized(param='access_token'):

    token = request.args.get(param)
    if not token:
        return False
    else:
        return verify_auth_token(token)
