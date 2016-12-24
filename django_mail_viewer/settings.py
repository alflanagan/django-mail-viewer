from __future__ import absolute_import, unicode_literals, print_function


from django.conf import settings


# The cache config from django.core.cache.caches to use for backends.cache.CacheBackend
# default to django.core.cache.caches['default']
MAILVIEWER_CACHE = getattr(settings, 'MAILVIEWER_CACHE', 'default')
