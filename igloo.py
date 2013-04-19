#!/usr/bin/env python

"""Igloo: a command line pastebin client.

Usage:
  igloo [-t TITLE] [-s SYNTAX] [-p PRIVACY] [-e EXPIRATION] [FILE] ...
  igloo (-l | --list)
  igloo (-r | --reset)
  igloo (-h | --help)
  igloo --version

Creates a pastebin from files or standard input and returns the pastebin's URL.
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
  -t TITLE --title=TITLE                  Title of snippet.
  -s SYNTAX --syntax=SYNTAX               Highlighting format.
  -p PRIVACY --privacy=PRIVACY            Privacy level [default: unlisted].
  -e EXPIRATION --expiration=EXPIRATION   Lifetime of snippet [default: 1H].
  -l --list                               View list of snippets by the current
                                          logged in user.
  -r --reset                              Reset pastebin credentials.

"""

__version__ = '0.0.8'


from getpass import getpass
from json import dump, load
from os import remove
from os.path import expanduser, join
from sys import stdin

try:
  from docopt import docopt
  from requests import Request, Session
  from requests.exceptions import Timeout
except ImportError:
  # probably in setup.py
  pass


class PasteError(Exception):

  pass


class Client(object):

  """Pastebin API client."""

  _key = None

  def __init__(self):
    self.session = Session()

  @property
  def key(self):
    """API developer and user keys.
    
    These are stored locally after the first time they are created.
    
    """
    path = join(expanduser('~'), '.igloo')
    if self._key is None:
      try:
        with open(path) as f:
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
          with open(path, 'w') as g:
            dump(key, g)
      self._key = key
    return self._key

  def _get_response(self, data):
    """Simple API response wrapper."""
    response = self.session.send(
      Request(
        'POST',
        'http://pastebin.com/api/api_post.php',
        data=dict(self.key.items() + (data or {}).items()),
      ).prepare()
    )
    if 'Bad API request' in response.content:
      raise PasteError(response.content)
    return response.content

  def create_paste(self, content, title=None, syntax=None,
                   privacy='unlisted', expiration='1H'):
    """Create a new paste on pastebin.com and return the corresponding URL.

    :param content: the content of the pastebin
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
    url = self._get_response(data)
    print 'Pastebin created! Url:\n%s' % (url, )

  def view_list_of_pastes(self):
    """View all pastes by logged in user."""
    print self._get_response({'api_option': 'list'})

  def reset_credentials(self):
    """Delete local cache of credentials."""
    path = join(expanduser('~'), '.igloo')
    try:
      remove(path)
    except OSError:
      print 'No credentials to delete.'
    else:
      print 'Credentials deleted.'


def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  client = Client()
  if arguments['--reset']:
    client.reset_credentials()
  elif arguments['--list']:
    client.view_list_of_pastes()
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
    url = client.create_paste(
      content,
      title=arguments['--title'],
      syntax=arguments['--syntax'],
      privacy=arguments['--privacy'],
      expiration=arguments['--expiration']
    )

if __name__ == '__main__':
  main()

