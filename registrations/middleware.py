import logging

logger = logging.getLogger(__name__)

class Log429Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 429:
            logger.warning(
                "429 HIT path=%s ip=%s user=%s",
                request.path,
                request.META.get("REMOTE_ADDR"),
                getattr(request.user, "username", "anon"),
            )

        return response
