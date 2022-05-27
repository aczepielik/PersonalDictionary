import configparser
import os
import sqlite3
from urllib.parse import urlparse, parse_qs, unquote_plus
from datetime import datetime, time
import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords

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
        'google': 'https%://%translate.google.pl/?sl=en&tl=pl&text=%',
        'google2': 'https%://%translate.google.pl/?hl=pl&sl=en&tl=pl&text=%'
    }

    extraction_functions = {
        'deepl': extract_deepl,
        'google': extract_google,
        'google2': extract_google
    }

    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
        
        self.dir = dir

        if os.path.exists(os.path.join(self.dir, 'last_check')):
            with open(os.path.join(self.dir, 'last_check'), 'r') as file:
                self.last_check = file.readline()
        else:
            self.last_check = 0
    
    def connect(self):
        try:
            self.conn = sqlite3.connect(self.db) # add error handling
            self.connected = True
        except sqlite3.OperationalError as e:
            print('Cannot connect to browser history')
            print(e)
            exit()

    def disconnect(self):
        self.conn.close()
        self.connected = False

    def update_last_check(self):
        self.last_check = int(datetime.now().timestamp() * 1e06)
        with open(os.path.join(self.dir, 'last_check'), 'w') as file:
                file.write(str(self.last_check))

    def _get_addresses_from_site(self):
        raise NotImplementedError

    
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

class FirefoxCrawler(Crawler):

    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary'), profile='Profile0'):
        
        super().__init__(dir)

        self.config = get_firefox_config()
        self.profile = profile
        self.db = get_firefox_history_db(self.config, self.profile)

        self.connected = False

    def _get_addresses_from_site(self, url, timestamp):
        
        if isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()
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

class ChromeCrawler(Crawler):
    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
    
        super().__init__(dir)

        self.db = os.path.join(os.environ["HOME"], '.config', 'google-chrome', 'Default', 'History')
        self.connected = False

    def _get_addresses_from_site(self, url, timestamp):
        
        if isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()
        assert self.connected
        cur = self.conn.cursor()

        cur.execute("""
        SELECT url 
        FROM urls 
        WHERE 
        url LIKE :ref_url 
        AND last_visit_time > :timestamp
        """,
        {"ref_url": url, "timestamp": int(timestamp)})
        data = cur.fetchall()

        cur.close()
        self.update_last_check()

        return data
        
class KindleCrawler(Crawler):
    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
        raise NotImplementedError