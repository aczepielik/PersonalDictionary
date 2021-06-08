import configparser
import os
import sqlite3
import itertools
import re


def get_firefox_config():
    firefox_config = configparser.ConfigParser()

    path = os.path.join(os.environ['HOME'], '.mozilla', 'firefox', 'profiles.ini')
    firefox_config.read(path)

    return firefox_config

def get_firefox_history_db(firefox_config, profile='Profile0'):
    
    try:
        dir = firefox_config.get(profile, 'Path')
    except:
        raise ValueError('Profile not found or incomplete')

    home = os.environ['HOME']

    return os.path.join(home, '.mozilla', 'firefox', dir, 'places.sqlite')

class Crawler:

    dictionary_urls = (
        'http%://%deepl.com/translator#en/pl/%',
        'https%://%translate.google.pl/?sl=en&tl=pl&text=%'
    )

    def __init__(self, profile='Profile0'):
        self.config = get_firefox_config()
        self.profile = profile
        self.db = get_firefox_history_db(self.config, self.profile)

        self.connected = False
    
    def connect(self):
        self.conn = sqlite3.connect(self.db) # add error handling
        self.connected = True

    def disconnect(self):
        self.conn.close()
        self.connected = False

    def _get_addresses_from_site(self, url, date):

        assert self.connected
        cur = self.conn.cursor()

        cur.execute("SELECT url FROM moz_places WHERE url LIKE :ref_url", {"ref_url": url})
        data = cur.fetchall()

        cur.close()
        return data
    
    def _get_addresses(self, date):
        
        addresses = map(lambda x: self._get_addresses_from_site(x, date), self.dictionary_urls)
        return list(itertools.chain(addresses))

    def get_queries(self, date):
        pass

class DictionaryConnection:

    def __init__(self, output_dir):
        self.apikey = None



