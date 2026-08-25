"""Absolute URLs for emails / copy text.

FRONTEND_URL (from .env / Vercel env) wins; otherwise fall back to the current
request host. Set it in production (e.g. https://sst.aicentre.org) so links in
emails never point at a preview deployment or an internal IP.
"""
from flask import current_app, request, url_for


def frontend_base():
    base = (current_app.config.get('FRONTEND_URL') or '').rstrip('/')
    if base:
        return base
    return request.url_root.rstrip('/') if request else ''


def public_url(endpoint, **values):
    """url_for() made absolute against FRONTEND_URL."""
    return frontend_base() + url_for(endpoint, **values)
