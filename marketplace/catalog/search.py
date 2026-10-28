"""Product search helpers.

The catalog used to rely on a single ``icontains`` check.  This module keeps
the search database-agnostic while adding token matching, category matching,
simple Ukrainian/Russian/English synonyms and a prefix fallback for typos.
"""

import re
import unicodedata
from functools import reduce
from operator import and_

from django.db.models import Case, IntegerField, Q, Value, When

MAX_QUERY_LENGTH = 80
MAX_TOKENS = 6

STOP_WORDS = {
    "а",
    "в",
    "від",
    "для",
    "до",
    "з",
    "і",
    "й",
    "на",
    "по",
    "та",
    "у",
    "and",
    "for",
    "the",
    "with",
}

# Keys and values are lowercase.  Values intentionally include the other
# language so a query such as "телефон" also finds "смартфон" / "phone".
SEARCH_SYNONYMS = {
    "телефон": ("смартфон", "phone", "mobile"),
    "смартфон": ("телефон", "phone", "mobile"),
    "навушники": ("headphones", "earbuds", "наушники"),
    "наушники": ("навушники", "headphones", "earbuds"),
    "ноутбук": ("laptop", "notebook", "ноут"),
    "ноут": ("ноутбук", "laptop", "notebook"),
    "комп'ютер": ("computer", "pc", "компьютер"),
    "компьютер": ("комп'ютер", "computer", "pc"),
    "холодильник": ("fridge", "refrigerator", "холодильник"),
    "пральна": ("washing", "стиральная"),
    "стиральная": ("пральна", "washing"),
    "пилосос": ("vacuum", "пылесос"),
    "пылесос": ("пилосос", "vacuum"),
    "колонка": ("speaker", "колонка"),
    "камера": ("camera", "камера"),
    "телевізор": ("tv", "television", "телевизор"),
    "телевизор": ("телевізор", "tv", "television"),
    "кросівки": ("sneakers", "shoes", "кроссовки"),
    "кроссовки": ("кросівки", "sneakers", "shoes"),
    "взуття": ("shoes", "footwear", "обувь"),
    "обувь": ("взуття", "shoes", "footwear"),
    "одяг": ("clothing", "clothes", "одежда"),
    "одежда": ("одяг", "clothing", "clothes"),
    "футболка": ("t-shirt", "tshirt", "футболка"),
    "сукня": ("dress", "платье"),
    "платье": ("сукня", "dress"),
    "куртка": ("jacket", "куртка"),
    "штани": ("pants", "trousers", "брюки"),
    "брюки": ("штани", "pants", "trousers"),
    "іграшка": ("toy", "игрушка"),
    "игрушка": ("іграшка", "toy"),
    "крем": ("cream", "крем"),
    "парфуми": ("perfume", "духи"),
    "духи": ("парфуми", "perfume"),
    "кава": ("coffee", "кофе"),
    "кофе": ("кава", "coffee"),
    "чай": ("tea", "чай"),
    "інструмент": ("tool", "инструмент"),
    "инструмент": ("інструмент", "tool"),
    "дриль": ("drill", "дрель"),
    "дрель": ("дриль", "drill"),
    "генератор": ("generator", "генератор"),
    "корм": ("food", "feed", "корм"),
    "меблі": ("furniture", "мебель"),
    "мебель": ("меблі", "furniture"),
}


def normalize_query(value):
    """Return a compact, case-folded query safe for ORM lookups."""
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", str(value)).lower()
    value = value.replace("’", "'").replace("ʼ", "'").replace("`", "'")
    value = re.sub(r"[^\w\s'-]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())[:MAX_QUERY_LENGTH]


def query_tokens(query):
    """Split a normalized query into meaningful tokens."""
    tokens = [
        token
        for token in query.split()
        if len(token) >= 2 and token not in STOP_WORDS
    ]
    return tokens[:MAX_TOKENS]


def _search_conditions(query, tokens, *, fuzzy=False):
    conditions = []

    def add(condition, weight):
        conditions.append((condition, weight))

    # Whole-query matches are the strongest signal.
    add(Q(name__iexact=query), 240)
    add(Q(name__istartswith=query), 160)
    add(Q(name__icontains=query), 120)
    add(Q(category__name__icontains=query), 70)
    add(Q(description__icontains=query), 40)

    if len(tokens) > 1:
        all_tokens_in_name = reduce(
            and_, (Q(name__icontains=token) for token in tokens)
        )
        add(all_tokens_in_name, 100)

    for token in tokens:
        add(Q(name__icontains=token), 30)
        add(Q(category__name__icontains=token), 18)
        add(Q(description__icontains=token), 7)

        for synonym in SEARCH_SYNONYMS.get(token, ()):
            add(Q(name__icontains=synonym), 16)
            add(Q(category__name__icontains=synonym), 9)
            add(Q(description__icontains=synonym), 4)

    if fuzzy:
        # "ноутбк" -> "ноут", "телфон" -> "тел".  This is only used when the
        # primary search has no results, so it cannot pollute exact matches.
        for token in tokens:
            if len(token) < 4:
                continue
            prefix = token[: max(3, len(token) - 1)]
            add(Q(name__icontains=prefix), 9)
            add(Q(category__name__icontains=prefix), 5)
            add(Q(description__icontains=prefix), 2)

    return conditions


def _score_expression(conditions):
    score = Value(0, output_field=IntegerField())
    for condition, weight in conditions:
        score += Case(
            When(condition, then=Value(weight)),
            default=Value(0),
            output_field=IntegerField(),
        )
    return score


def _filter_expression(conditions):
    result = Q()
    for condition, _weight in conditions:
        result |= condition
    return result


def _apply_conditions(queryset, conditions):
    return queryset.annotate(search_score=_score_expression(conditions)).filter(
        _filter_expression(conditions)
    )


def search_products(queryset, query):
    """Filter and rank ``queryset`` for a normalized search query.

    The returned queryset always has a ``search_score`` annotation.  If the
    strict search finds nothing, a prefix-based fallback handles simple typos.
    """
    tokens = query_tokens(query)
    strict = _apply_conditions(
        queryset, _search_conditions(query, tokens, fuzzy=False)
    )
    if strict.exists():
        return strict

    if any(len(token) >= 4 for token in tokens):
        return _apply_conditions(
            queryset, _search_conditions(query, tokens, fuzzy=True)
        )

    return strict
