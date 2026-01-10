import os

NODE_JS_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), 'node')

from .scrapers import get_scraper, Scraper

__all__ = ['NODE_JS_SCRIPTS_DIR', 'get_scraper', 'Scraper']
