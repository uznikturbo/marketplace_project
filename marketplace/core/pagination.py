"""Small helpers for paginated list views."""

from django.core.paginator import Paginator


def paginate(request, queryset, per_page):
    """Return ``(page_obj, page_range)`` for the current request.

    ``page_range`` is already elided around the current page, so templates do
    not need to call methods with arguments (which Django templates cannot do).
    """
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    return page_obj, paginator.get_elided_page_range(page_obj.number)
