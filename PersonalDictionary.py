#!/home/adam/anaconda3/envs/personaldict/bin/python

import configparser
import os
import sqlite3
import shutil
import requests
import json
import click
from datetime import datetime, time
from urllib.parse import urlparse, parse_qs, unquote_plus
import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords
import rich
import re
  

STOP_WORDS = stopwords.words('english')


bold = lambda x: '[bold]' + x + '[/bold]'
italic = lambda x: '[italic]' + x + '[/italic]'

def main_tuple_style(tup):
    return bold(tup[0]) + ', ' + italic(tup[1])

def secondary_tuples_style(tup_list):
    single_tuple = lambda tup: tup[0] + ', ' + italic(tup[1])

    return '; '.join(list(map(single_tuple, tup_list)))

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

    style_dict = {
        'main': main_tuple_style,
        'secondary': secondary_tuples_style,
        'definitions': lambda x: '\n'.join(x)
    }

    regex_filter = re.compile('[,\.!?/~]')

    def __init__(self, dir=os.path.join(os.environ["HOME"], '.personaldictionary')):
        api_config_path = os.path.join(dir, ".keys")
        self.meta_dict_path = os.path.join(dir, 'meta.db')

        api_config = configparser.ConfigParser()
        api_config.read(api_config_path)

        self.config = api_config
        self.dir = dir

        try:
            self.meta_dict = sqlite3.connect(self.meta_dict_path)
            cur = self.meta_dict.cursor()

            create_words_table = """
            CREATE TABLE IF NOT EXISTS words (
                id integer PRIMARY KEY,
                word text NOT NULL,
                entry_id text NOT NULL
            );
            """

            create_word_entries_table = """
            CREATE TABLE IF NOT EXISTS word_entries (
                entry_id text PRIMARY KEY,
                file text
            )
            """

            cur.execute(create_words_table)
            cur.execute(create_word_entries_table)
            cur.close()

        except sqlite3.OperationalError as e:
            print('Cannot connect to local disctionary')
            print(e)
            exit()

    def disconnet(self):
        self.meta_dict.close()


    def _check_dictionary(self, word, endpoint='Dictionary'):
        url = self.endpoints[endpoint]

        res = requests.get(
            url + word,
            {'key': self.config.get('Merriam-Webster', endpoint)}
            )

        res.raise_for_status()

        parsed = res.json()

        if len(parsed) == 0:
            raise ValueError
        elif not isinstance(parsed[0], dict):
            raise ValueError
        elif not ('meta' in parsed[0].keys()):
            raise ValueError
        else:
            return parsed

    def _check_metadict(self, word):
        cur = self.meta_dict.cursor()
        
        cur.execute("""
        SELECT file
        FROM words
        LEFT JOIN  word_entries
        ON words.entry_id = word_entries.entry_id
        WHERE 
        words.word = :word
        """,
        {"word": word})

        data = cur.fetchall()
        cur.close()

        return data

    def _check_cache(self, word):
        files = self._check_metadict(word)

        if len(files) == 0:
            return None
        else:
            results = []
            for file in files:
                with open(os.path.join(self.dir, '.data', file[0]), 'r') as f:
                    results.append(json.load(f))
            
            return results

    def _save_entry(self, entry):

        id = self.regex_filter.sub('', entry['meta']['id'])
        entry_path = os.path.join(self.dir, ".data", id + '.json')

        with open(entry_path, 'w+') as file:
            json.dump(entry, file)

    def _save_word(self, word, entries):
        cur = self.meta_dict.cursor()

        for entry in entries:
            id = self.regex_filter.sub('', entry['meta']['id'])

            stems = set(entry['meta']['stems'] + [word])

            for stem in stems:
                cur.execute(
                    "DELETE FROM words WHERE word = :word AND entry_id = :id",
                    {"word": stem, "id": id}
                )
                cur.execute(
                    "DELETE FROM word_entries WHERE entry_id = :id",
                    {"id": id}
                )
            
                cur.execute(
                    "INSERT INTO words (word, entry_id) VALUES (:word, :id)",
                    {"word": stem, "id": id}
                )
                cur.execute(
                    "INSERT INTO word_entries (entry_id, file) VALUES (:id, :path)",
                    {"id": id, "path": id + '.json'}
                )

            self._save_entry(entry)
        
        cur.close()
        self.meta_dict.commit()

    def remove_word(self, word):
        cur = self.meta_dict.cursor()
        cur.execute("DELETE FROM words WHERE word = :word", {"word": word})
        cur.close()

        self.meta_dict.commit()

    def clean_dictionary(self):
        cur = self.meta_dict.cursor()

        cur.execute("""
        SELECT file 
        FROM word_entries 
        LEFT JOIN words 
            ON word_entries.entry_id = words.entry_id 
        WHERE words.word IS NULL
        """)

        files_to_delete = cur.fetchall()

        cur.execute("""
        DELETE FROM word_entries
        WHERE file IN (
            SELECT file 
            FROM word_entries 
            LEFT JOIN words 
            ON word_entries.entry_id = words.entry_id 
            WHERE words.word IS NULL
        )
        """)

        cur.close()
        self.meta_dict.commit()

        for file in files_to_delete:
            os.remove(os.path.join(self.dir, '.data', file))


    def purge_dictionary(self):
        shutil.rmtree(os.path.join(self.dir, ".data"))
        
        cur = self.meta_dict.cursor()

        cur.execute('DROP TABLE IF EXISTS words')
        cur.execute('DROP TABLE IF EXISTS word_entries')

        cur.close()
        self.meta_dict.commit()

    def parse_entry(self, entry):
        parsed = {
            'main': (entry.get('meta', {}).get('stems',[''])[0], entry.get('fl', '')),
            'secondary': [(ure.get('ure', ''), ure.get('fl', '')) for ure in entry.get('uros', [])],
            'definitions': [str(i+1) + '. ' + shortdef.capitalize()\
                 for i, shortdef in enumerate(entry.get('shortdef',[]))]
        }

        return parsed

    def print_word(self, parsed):
        for key, val in parsed.items():
            styled_text = self.style_dict[key](val)
            rich.print(styled_text)


    def check_word(self, word, force=False, prompt=True, save=True):
        
        if not force:
            entry = self._check_cache(word)
            from_cache = True
        else:
            entry = None
        
        if entry is None:
            try:
                entry = self._check_dictionary(word)

                if not isinstance(entry, list):
                    raise ValueError
                elif not isinstance(entry[0], dict):
                    raise ValueError
                elif entry[0].get('meta', None) is None:
                    raise ValueError
                else:
                    pass
                from_cache = False
            except ValueError:
                print(word + ' not found')
                return 0

        if prompt:
            print('')
            for single_entry in entry:
                parsed = self.parse_entry(single_entry)
                self.print_word(parsed)
                print('')
        
        if save and not from_cache:
            self._save_word(word, entry)

    def count_words(self):
        cur = self.meta_dict.cursor()

        cur.execute('SELECT COUNT(*) total FROM words')
        count = cur.fetchall()

        if len(count) == 0:
            count = 0
        else:
            count = count[0][0]

        cur.close()
        return count

    def list_words(self, n):
        cur = self.meta_dict.cursor()

        cur.execute('SELECT word FROM words LIMIT :n', {"n": n})
        words = cur.fetchall()

        cur.close()
        return words

#-- interface

@click.group()
def cli():
    pass

@cli.command(help="Scan the browser's history in search for English words checked in online translators.")
@click.option('-f', '--from', 'from_timestamp',
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="When to start scanning browser history from.")
def scan(from_timestamp):
    Crw = Crawler()
    MW = DictionaryConnection()

    Crw.connect()

    queries = Crw.get_queries(from_timestamp)

    for word in queries:
        MW.check_word(word)
    print(from_timestamp)
    Crw.disconnect()
    MW.disconnet()

@cli.command(help="Check the English word in online dictionary")
@click.argument('word')
@click.option('--force-online', 'online', is_flag=True, default=False)
@click.option('--prompt/--no-prompt', 'prompt', default=True)
@click.option('--save/--no-save', 'save', default=True)
def check(word, online, prompt, save):
    MW = DictionaryConnection()
    MW.check_word(word, online, prompt, save)
    MW.disconnet()

@cli.command(help='Count words in the cached dictionary.')
def count_words():
    MW = DictionaryConnection()
    print(MW.count_words())
    MW.disconnet()

@cli.command(help='Show n words from the local cache')
@click.argument('n_words')
def list_words(n_words=5):
    MW = DictionaryConnection()
    print(MW.list_words(n_words))
    MW.disconnet()


if __name__ == "__main__":
    cli()
    #check('computer', False, True, False)
