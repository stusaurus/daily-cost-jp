"""Tie recommendations to one freshly fetched catalog without changing raw data."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime


def catalog_digest(catalog):
    content = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def provenance(catalog):
    return {
        'source_updated_at': catalog['updated_at'],
        'catalog_sha256': catalog_digest(catalog),
        'build_sha': os.environ.get('GITHUB_SHA', ''),
        'build_run_id': os.environ.get('GITHUB_RUN_ID', ''),
    }


def freshness_errors(payload, catalog, *, not_before=None, expected_sha='', expected_run_id=''):
    errors = []
    if payload.get('catalog_sha256') != catalog_digest(catalog):
        errors.append('Recommendations belong to a different catalog')
    if payload.get('source_updated_at') != catalog.get('updated_at'):
        errors.append('Recommendation source timestamp differs from catalog')
    try:
        source = datetime.fromisoformat(catalog['updated_at'])
        generated = datetime.fromisoformat(payload['generated_at'])
        if source.tzinfo is None or generated.tzinfo is None or generated < source:
            raise ValueError('Invalid generation order/timezone')
        if payload.get('date') != generated.date().isoformat():
            raise ValueError('Date differs from generation time')
        if not_before is not None and (source < not_before or generated < not_before):
            errors.append('Catalog/recommendations are older than the required refresh')
    except (KeyError, TypeError, ValueError):
        errors.append('Missing or invalid generation timestamps')
    if expected_sha and payload.get('build_sha') != expected_sha:
        errors.append('Unexpected deployed commit')
    if expected_run_id and payload.get('build_run_id') != str(expected_run_id):
        errors.append('Unexpected deployed workflow run')
    return errors
