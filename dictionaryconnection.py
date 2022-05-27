import os
import configparser
import sqlite3
import shutil
import requests
import json
import re
import rich
from styles import main_tuple_style, secondary_tuples_style

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