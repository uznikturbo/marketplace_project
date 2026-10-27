import zoneinfo

from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.session.get("user_timezone")

        if tzname:
            try:
                timezone.activate(zoneinfo.ZoneInfo(tzname))
            except (zoneinfo.ZoneInfoNotFoundError, ValueError, TypeError):
                timezone.deactivate()
                request.session.pop("user_timezone", None)
        else:
            timezone.deactivate()

        return self.get_response(request)
