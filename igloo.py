#!/usr/bin/env python

"""Igloo: a command line pastebin client.

Usage:
  igloo [-t TITLE] [-s SYNTAX] [-p PRIVACY] [-e EXPIRATION] [-f FILE]
  igloo (-l | --list)
  igloo (-h | --help)
  igloo --version

Options:
  -h --help                               Show this screen.
  --version                               Show version.
  -l --list                               View list of snippets.
  -t TITLE --title=TITLE                  Title of snippet.
  -s SYNTAX --syntax=SYNTAX               Highlighting format.
  -p PRIVACY --privacy=PRIVACY            Privacy level [default: unlisted].
  -e EXPIRATION --expiration=EXPIRATION   Lifetime of snippet [default: 1H].
  -f FILE --file=FILE                     File to copy. Standard input will be
                                          used if no file is specified.

"""

__version__ = '0.0.1'


from docopt import docopt
from getpass import getpass
from json import dump, load
from requests import Request, Session
from requests.exceptions import Timeout
from sys import stdin


class PasteError(Exception):

  pass


class Client(object):

  def __init__(self, key_storage_path='key.json'):
    self.session = Session()
    self.key = self._get_key(key_storage_path)

  def _get_key(self, key_storage_path):
    try:
      with open(key_storage_path) as f:
        key = load(f)
    except IOError:
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
        with open(key_storage_path, 'w') as g:
          dump(key, g)
          print 'API keys stored in %r.' % (key_storage_path, )
    return key

  def _get_response(self, data):
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

  def view_list_of_pastes(self):
    print self._get_response({'api_option': 'list'})

def main():
  arguments = docopt(__doc__, version=__version__)
  client = Client()
  if arguments['--list']:
    client.view_list_of_pastes()
  else:
    filepath = arguments['--file']
    if filepath:
      with open(filepath) as f:
        content = f.read()
    else:
      content = stdin.read()
    url = client.create_paste(
      content,
      title=arguments['--title'],
      syntax=arguments['--syntax'],
      privacy=arguments['--privacy'],
      expiration=arguments['--expiration']
    )
    print 'Pastebin created! Url: %s' % (url, )

if __name__ == '__main__':
  main()
