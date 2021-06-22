#!/home/adam/anaconda3/envs/personaldict/bin/python

import configparser
import os
import sqlite3
import itertools
import re
import shutil
import requests
import json
import click
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote_plus
import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
  
lemmatizer = WordNetLemmatizer()
STOP_WORDS = stopwords.words('english')


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

def extract_google(url):
    parsed_url = urlparse(url)
    phrase = parse_qs(parsed_url.query).get('text')

    return unquote_plus(' '.join(phrase))

def extract_deepl(url):
    parsed_url = urlparse(url)
    phrase = parsed_url.fragment.replace('en/pl/', '')

    return unquote_plus(phrase)

class Crawler:

    dictionary_urls = {
        'deepl': 'http%://%deepl.com/translator#en/pl/%',
        'google': 'https%://%translate.google.pl/?sl=en&tl=pl&text=%'
    }

    extraction_functions = {
        'deepl': extract_deepl,
        'google': extract_google
    }

    def __init__(self, profile='Profile0', dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
        
        self.config = get_firefox_config()
        self.profile = profile
        self.db = get_firefox_history_db(self.config, self.profile)

        self.connected = False

        self.dir = dir

        if os.path.exists(os.path.join(self.dir, 'last_check')):
            with open(os.path.join(self.dir, 'last_check'), 'r') as file:
                self.last_check = file.readline()
        else:
            self.last_check = 0
    
    def connect(self):
        self.conn = sqlite3.connect(self.db) # add error handling
        self.connected = True

    def disconnect(self):
        self.conn.close()
        self.connected = False

    def update_last_check(self):
        self.last_check = int(datetime.now().timestamp() * 1e06)
        with open(os.path.join(self.dir, 'last_check'), 'w') as file:
                file.write(str(self.last_check))

    def _get_addresses_from_site(self, url, timestamp):

        assert self.connected
        cur = self.conn.cursor()

        cur.execute("""
        SELECT url 
        FROM moz_places 
        WHERE 
        url LIKE :ref_url 
        AND last_visit_date > :timestamp
        """,
        {"ref_url": url, "timestamp": int(timestamp)})
        data = cur.fetchall()

        cur.close()
        self.update_last_check()

        return data
    
    def _get_addresses(self, timestamp):
        
        addresses = {service: list(sum(self._get_addresses_from_site(url, timestamp), ()))
            for service, url in self.dictionary_urls.items()}
        return addresses

    def get_queries(self, timestamp=None):
        
        if timestamp is None:
            timestamp = self.last_check 
        
        urls = self._get_addresses(timestamp)

        raw_queries = [self.extraction_functions[key](value) for key, values in urls.items() for value in values]
        
        tokenized_queries = [word_tokenize(phrase.lower().replace('\\n', '')) for phrase in raw_queries]
        
        cleaned_queries = [word for word in set(sum(tokenized_queries, []))
            if word not in STOP_WORDS and word.isalnum()]
        
        return cleaned_queries

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

        if os.path.exists(self.meta_dict_path):
            with open(self.meta_dict_path, 'r') as file:
                self.meta_dict = json.load(file)
        else:
            self.meta_dict = {}
            with open(self.meta_dict_path, 'w') as meta_file:
                json.dump(self.meta_dict, meta_file)

        if not os.path.exists(os.path.join(self.dir, '.data')):
            os.mkdir(os.path.join(self.dir, '.data'))


    def _check_dictionary(self, word, endpoint='Dictionary'):
        url = self.endpoints[endpoint]

        res = requests.get(
            url + word,
            {'key': self.config.get('Merriam-Webster', endpoint)}
            )

        res.raise_for_status()

        parsed = res.json()

        # raise error for bad response

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

        with open(self.meta_dict_path, 'w') as meta_file:
            json.dump(self.meta_dict, meta_file)

    def remove_word(self, word):
        word_path = os.path.join(self.dir, ".data", word + '.json')
        assert os.path.exists(word_path)
        os.remove(word_path)

        self.meta_dict.pop(word)

        with open(self.meta_dict_path, 'w') as meta_file:
            json.dump(self.meta_dict, meta_file)

    def clear_dictionary(self):
        shutil.rmtree(os.path.join(self.dir, ".data"))
        
        self.meta_dict = {}

        with open(self.meta_dict_path, 'w') as meta_file:
            json.dump(self.meta_dict, meta_file)


    def check_word(self, word, force=False, prompt=True, save=True):
        # to do: adopt to one to many relation
        if not force:
            entry = self._check_cache(word)
            from_cache = True
        else:
            entry = None
        
        if entry is None:
            entry = self._check_dictionary(word) # to do: add error handling
            from_cache = False

        if prompt:
            print(entry)
        
        if save and not from_cache:
            self._save_word(word, entry)

if __name__ == "__main__":

    Crw = Crawler()
    Crw.connect()

    print(Crw.last_check)
    Crw.last_check = 0
    
    query1 = Crw.get_queries()
    print(len(query1))

    print(Crw.last_check)
    #queries = Crw.get_queries()

    Crw.disconnect()

    Crw2 = Crawler()

    print(Crw2.last_check)
    Crw2.connect()

    query2 = Crw2.get_queries()
    print(len(query2))

    print(Crw2.last_check)
    
    #MW = DictionaryConnection()

    #for word in queries[:5]:
    #    MW.check_word(word)

    #MW.clear_dictionary()





