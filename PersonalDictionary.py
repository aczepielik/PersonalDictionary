import configparser
import os
import sqlite3


def get_firefox_config():
    firefox_config = configparser.ConfigParser()
    firefox_config.read('/home/adam/.mozilla/firefox/profiles.ini')

    return firefox_config

def get_default_history_db(firefox_config, profile='Profile0'):
    
    dir = firefox_config.get(profile, 'Path')
    home = os.environ['HOME']

    return os.path.join(home, '.mozilla', 'firefox', dir, 'places.sqlite')

def get_firefox_history_connection():
    conf = get_firefox_config()
    file = get_default_history_db(conf)

    connection = sqlite3.connect(file)
    return connection

def get_urls(conn):
    cur = conn.cursor()

    cur.execute("SELECT url FROM moz_places WHERE url LIKE 'http%://%deepl.com/translator#en/pl/%'")
    data = cur.fetchall()

    return data



