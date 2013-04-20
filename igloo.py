#!/usr/bin/env python

"""Igloo: a command line pastebin client.

Usage:
  igloo [-o] [-t TITLE] [-s SYNTAX] [-p PRIVACY] [-e EXPIRATION] [FILE] ...
  igloo (-d KEY | --download=KEY)
  igloo (-l | --list)
  igloo (-r | --reset)
  igloo (-h | --help)
  igloo --version

Creates a paste on pastebin.com from files or standard input and returns the
paste's URL or opens the corresponding page in your browser.

You must have a pastebin.com account to use igloo. The first time you use
igloo you will be prompted for your api developer key (which can be found at
http://pastebin.com/api) along with your user name and password. Igloo then
stores the necessary pastebin credentials in ``~/.igloo`` for later use.

Examples:
  igloo my_file.txt
  igloo -t 'code snippet' -s python -p private < my_code.py
  echo 'hello world!' | igloo

Arguments:
  FILE                                    File(s) to copy. Multiple files will
                                          have their contents joined by
                                          newlines. If no file is specified
                                          standard input will be used instead.

Options:
  -h --help                               Show this screen.
  --version                               Show version.
  -o --open                               Open browser after creating paste.
  -t TITLE --title=TITLE                  Title of snippet.
  -s SYNTAX --syntax=SYNTAX               Highlighting format.
  -p PRIVACY --privacy=PRIVACY            Privacy level [default: unlisted].
  -e EXPIRATION --expiration=EXPIRATION   Lifetime of snippet [default: 1H].
  -d KEY --download=KEY                   Get raw data from a paste's key.
                                          The key is the last part of the URL.
  -l --list                               View list of pastes by the current
                                          logged in user.
  -r --reset                              Reset pastebin credentials.

"""

__version__ = '0.0.13'


from getpass import getpass
from json import dump, load
from os import remove
from os.path import expanduser, join
from sys import stdin
from time import time
from webbrowser import open as open_webbrowser
from xml.etree.ElementTree import fromstring

try:
  from docopt import docopt
  from requests import Session
  from requests.exceptions import Timeout
except ImportError:
  # probably in setup.py
  pass


class PasteError(Exception):

  """Generic Igloo Error."""

  pass


class Client(object):

  """Pastebin API client."""

  path = join(expanduser('~'), '.igloo')

  _key = None

  def __init__(self):
    self.session = Session()

  @property
  def key(self):
    """API developer and user keys.

    These are stored locally after the first time they are created.

    """
    if self._key is None:
      try:
        with open(self.path) as f:
          key = load(f)
      except IOError:
        print 'Generating new credentials:'
        print 'Cf. http://pastebin.com/api to find the required keys.'
        try:
          api_dev_key = raw_input('API dev key: ')
          req = self.session.post(
            'http://pastebin.com/api/api_login.php',
            data={
              'api_dev_key': api_dev_key,
              'api_user_name': raw_input('API user name: '),
              'api_user_password': getpass('API user password: '),
            }
          )
        except Timeout:
          raise PasteError('Unable to connect to server.')
        else:
          if 'Bad API request' in req.content:
            raise PasteError(req.content)
          key = {
            'api_dev_key': api_dev_key,
            'api_user_key': req.content,
          }
          with open(self.path, 'w') as g:
            dump(key, g)
      self._key = key
    return self._key

  def _get_response(self, data):
    """Simple API response wrapper."""
    data = self.session.post(
      'http://pastebin.com/api/api_post.php',
      data=dict(self.key.items() + (data or {}).items()),
    ).content
    if 'Bad API request' in data or 'Post limit' in data:
      raise PasteError(data)
    return data

  def create(self, content, title=None, syntax=None, privacy='unlisted',
             expiration='1H'):
    """Create a new paste on pastebin.com and return the corresponding URL.

    :param content: the content of the paste
    :rtype: str

    """
    data = {
      'api_option': 'paste',
      'api_paste_code': content,
      'api_paste_name': title or '',
    }
    privacy_mapping = {'public': 0, 'unlisted': 1, 'private': 2}
    try:
      privacy_level = privacy_mapping[privacy]
    except KeyError:
      raise PasteError(
        'Invalid privacy argument: %r. Valid values: %s.' %
        (privacy, ', '.join(privacy_mapping.keys()))
      )
    else:
      data['api_paste_private'] = privacy_level
    expiration_values = ['10M', '1H', '1D', '1W', '2W', '1M', 'N']
    if not expiration in expiration_values:
      raise PasteError(
        'Invalid expiration argument: %r. Valid values: %s.' %
        (expiration, ', '.join(expiration_values))
      )
    else:
      data['api_paste_expire_date'] = expiration
    if syntax:
      data['api_paste_format'] = syntax
    return self._get_response(data)

  def get_list_of_pastes(self):
    """View all pastes by logged in user."""
    data = self._get_response({'api_option': 'list'})
    root = fromstring('<data>%s</data>' % (data, ))
    pastes = root.getchildren()
    header = (
      '\n%10s %4s %2s %3s %-25s %s\n' %
      ('key', 'min', 'pr', 'hit', 'url', 'title')
    )
    rows = []
    now = time()
    for paste in pastes:
      tags = paste.getchildren()
      key = tags[0].text
      mins = (now - int(tags[1].text)) / 60
      title = tags[2].text or ''
      pr = tags[5].text
      url = tags[8].text[7:]
      hits = tags[9].text
      rows.append(
        '%10s %4i %2s %3s %-25s %s' %
        (key, mins, pr, hits, url, title)
      )
    if rows:
      return header + '\n'.join(rows)
    else:
      return 'No pastes found.'

  def get_raw_paste(self, key):
    """Get the raw content from a paste's key."""
    resp = self.session.get('http://pastebin.com/raw.php', params={'i': key})
    data = resp.content
    if 'Unknown Paste ID!' in data:
      return 'No paste found.'
    else:
      return data
    
  def reset_credentials(self):
    """Delete local cache of credentials."""
    try:
      remove(self.path)
    except OSError:
      return 'No credentials to delete.'
    else:
      return 'Credentials deleted.'


def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  client = Client()
  if arguments['--reset']:
    print client.reset_credentials()
  elif arguments['--list']:
    print client.get_list_of_pastes()
  elif arguments['--download']:
    print client.get_raw_paste(arguments['--download'])
  else:
    filepaths = arguments['FILE']
    if filepaths:
      contents = []
      for filepath in filepaths:
        with open(filepath) as f:
          contents.append(f.read())
      content = '\n\n'.join(contents)
    else:
      content = stdin.read()
    url = client.create(
      content,
      title=arguments['--title'],
      syntax=arguments['--syntax'],
      privacy=arguments['--privacy'],
      expiration=arguments['--expiration']
    )
    if arguments['--open']:
      open_webbrowser(url)
    else:
      print 'Paste successfully created! URL: %s' % (url[7:], )

if __name__ == '__main__':
  main()
