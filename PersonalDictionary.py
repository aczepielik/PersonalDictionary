#!/home/adam/anaconda3/envs/personaldict/bin/python

import click
from datetime import datetime, time
import re

from styles import main_tuple_style, secondary_tuples_style
from crawlers import FirefoxCrawler, ChromeCrawler
from dictionaryconnection import DictionaryConnection


# -- interface


@click.group()
def cli():
    pass


@cli.command(
    help="Scan the browser's history in search for English words checked in online translators."
)
@click.option(
    "-f",
    "--from",
    "from_timestamp",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="When to start scanning browser history from.",
)
def scan(from_timestamp):
    crawlers = [FirefoxCrawler(), ChromeCrawler()]
    MW = DictionaryConnection()
    queries = []

    for Crw in crawlers:
        Crw.connect()  # TO DO: add error handling
        queries += Crw.get_queries(from_timestamp)
        Crw.disconnect()

    for word in queries:
        MW.check_word(word)
    print(from_timestamp)
    MW.disconnet()


@cli.command(help="Check the English word in online dictionary")
@click.argument("word")
@click.option("--force-online", "online", is_flag=True, default=False)
@click.option("--prompt/--no-prompt", "prompt", default=True)
@click.option("--save/--no-save", "save", default=True)
def check(word, online, prompt, save):
    MW = DictionaryConnection()
    MW.check_word(word, online, prompt, save)
    MW.disconnet()


@cli.command(help="Count words in the cached dictionary.")
def count_words():
    MW = DictionaryConnection()
    print(MW.count_words())
    MW.disconnet()


@cli.command(help="Show n words from the local cache")
@click.argument("n_words")
def list_words(n_words=5):
    MW = DictionaryConnection()
    print(MW.list_words(n_words))
    MW.disconnet()


if __name__ == "__main__":
    cli()
    # check('computer', False, True, False)
