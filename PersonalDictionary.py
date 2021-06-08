#!/usr/bin/python3

import configparser
import os
import sqlite3
import itertools
import re
import requests
import json
import click


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

    endpoints = {
        'Dictionary': 'https://www.dictionaryapi.com/api/v3/references/collegiate/json/',
        'Thesaurus': 'https://www.dictionaryapi.com/api/v3/references/thesaurus/json/'
    }

    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
        api_config_path = os.path.join(dir, ".keys")
        self.meta_dict_path = os.path.join(dir, 'meta.json')

        api_config = configparser.ConfigParser()
        api_config.read(api_config_path)

        self.config = api_config
        self.dir = dir

        with open(self.meta_dict_path, 'r') as file:
            self.meta_dict = json.load(file)

    def _check_dictionary(self, word, endpoint='Dictionary'):
        url = self.endpoints[endpoint]

        res = requests.get(
            url + word,
            {'key': self.config.get('Merriam-Webster', endpoint)}
            )

        res.raise_for_status()

        parsed = res.json()

        return parsed

    def _check_cache(self, word):
        if word in self.meta_dict:
            entry_file= self.meta_dict.get(word)
            entry_path = os.path.join(self.dir, entry_file)

            with open(entry_path, 'r') as file:
                entry = json.load(file)

            return entry
        else:
            return None

    def _save_word(self, word, entry):
        word_path = os.path.join(self.dir, ".data", word + '.json')

        with open(word_path, 'w+') as file:
            json.dump(entry, file)
            
        self.meta_dict[word] = os.path.join(".data", word + '.json')

        with open(self.meta_dict_path, 'w+') as meta_file:
            json.dump(self.meta_dict, meta_file)

    def check_word(self, word, force=False, prompt=True, save=True):

        if not force:
            entry = self._check_cache(word)
            from_cache = True
        else:
            entry = None
        
        if entry is None:
            entry = self._check_dictionary(word)
            from_cache = False

        if prompt:
            print(entry)
        
        if save and not from_cache:
            self._save_word(word, entry)

if __name__ == "__main__":
    
    MW = DictionaryConnection()

    MW.check_word('voluminous')
    MW.check_word('voluminous')





