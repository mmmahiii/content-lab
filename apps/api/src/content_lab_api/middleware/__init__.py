"""HTTP middleware for the Content Lab API."""

from content_lab_api.middleware.request_context import RequestContextMiddleware

__all__ = ["RequestContextMiddleware"]
