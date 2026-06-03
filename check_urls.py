from django.urls import get_resolver

def list_urls(resolver, prefix=''):
    for pattern in resolver.url_patterns:
        from django.urls import URLResolver, URLPattern
        if isinstance(pattern, URLResolver):
            list_urls(pattern, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            print(prefix + str(pattern.pattern))

list_urls(get_resolver())