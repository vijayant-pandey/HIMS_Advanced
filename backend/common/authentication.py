from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """Session authentication that answers 401 (not 403) for unauthenticated requests.

    DRF downgrades NotAuthenticated to 403 when the authenticator has no challenge header,
    which would make "not signed in" indistinguishable from "not permitted" for the SPA.
    """

    def authenticate_header(self, request):
        return "Session"


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "common.authentication.SessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "hims_session"}
