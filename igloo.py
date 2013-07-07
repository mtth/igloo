#!/usr/bin/env python

"""Igloo: a command line SCP client.

Usage:
  igloo [-dflmrqt] [-p PROFILE | -u URL] ([-in] -e EXPR | FILENAME ...)
  igloo (-s | --stream) [-bdr] [-p PROFILE | -u URL] FILENAME
  igloo (-c | --config) [add URL [PROFILE] | delete PROFILE | list]
  igloo -h | --help | -v | --version

Arguments:
  FILENAME                      The file to transfer.

Options:
  -b --binary                   Don't decode stdout (when piping binary files).
  -c --config                   Configuration mode.
  -d --debug                    Enable full exception traceback.
  -e EXPR --expr=EXPR           Regular expression to filter filenames.
  -f --force                    Force overwrite.
  -h --help                     Show this screen.
  -i --case-insensitive         Case insensitive matching.
  -l --list                     Only show matching filenames.
  -m --move                     Delete origin copy.
  -n --no-match                 Inverse match.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  -q --quiet                    No output.
  -r --remote                   Remote mode.
  -s --stream                   Streaming mode.
  -u URL --url=URL              Url to SCP to (will override any profile).
  -v --version                  Show version.

Todo:
  -t --track                    Track progress.
  -z --zip                      Zip on the fly.
  --clean                       Like list but remove.
  Make binary option automatic (checking if output is piped).

"""

__version__ = '0.1.0'


from codecs import getwriter
from getpass import getuser
from locale import getpreferredencoding
from os import environ, listdir, remove
from os.path import exists, expanduser, join
from re import compile as re_compile, IGNORECASE
from socket import error
from sys import stderr, stdin, stdout
from traceback import format_exc

try:
  from docopt import docopt
  from paramiko import SSHClient, SSHException
  from yaml import dump, load
except ImportError:
  pass # probably in setup.py


ERRORS = {
  0: 'something bad happened',
  1: 'unable to connect to %r@%r',
  2: 'remote file %r not found',
  3: 'local file %r not found',
  4: 'transfer interrupted',
  5: 'refusing to transfer directory. try with the --zip option',
  6: 'invalid remote folder %r',
  7: 'unable to decode received data. try with the --binary option',
  8: 'unable to load host keys from file %r',
  9: 'no configuration file found',
  10: 'profile %r not found in configuration file',
  11: 'local file %r would be overwritten by transfer (use --force)',
  12: 'remote file %r would be overwritten by transfer (use --force)',
}


def get_stream_writer(binary=False, writer=stdout):
  """Returns the stream writer used by the client."""
  if binary:
    return writer
  else:
    return getwriter(getpreferredencoding())(writer)

def write(iterable, writer, lazy_flush=True, format='%s\n'):
  """Write to stdout, handles enconding automatically."""
  for elem in iterable:
    writer.write(format % elem)
    if not lazy_flush:
      writer.flush()
  if lazy_flush:
    writer.flush()

def get_callback():
  """Callback factory function for ``sftp.put`` and ``sftp.get``."""
  writer = get_stream_writer()
  def callback(transferred, total):
    """Actual callback function."""
    progress = int(100 * float(transferred) / total)
    if progress < 100:
      writer.write(' %2i%%\r' % (progress, ))
    else:
      writer.write('      \r')
    writer.flush()
  return callback

def parse_url(url):
  """Parse URL into user, host and remote directory."""
  if '@' in url:
    user, url = url.split('@', 1)
  else:
    user = getuser()
  if ':' in url:
    host, path = url.split(':', 1)
  else:
    host = url
    path = '.'
  if not host:
    raise ValueError('Empty url')
  else:
    return user, host, path


class ClientError(Exception):

  """Base client error class.

  Stores the original traceback to be displayed in debug mode.

  """

  def __init__(self, number, details=()):
    super(ClientError, self).__init__('error: ' + ERRORS[number] % details)
    self.traceback = format_exc()


class Client(object):

  """API client."""

  ssh = None
  sftp = None

  def __init__(self, url, host_keys):
    self.user, self.host, self.path = parse_url(url)
    self.host_keys = host_keys

  def __enter__(self):
    self.ssh = SSHClient()
    try:
      self.ssh.load_host_keys(self.host_keys)
    except IOError:
      raise ClientError(8, (self.host_keys, ))
    try:
      self.ssh.connect(self.host, username=self.user)
    except (SSHException, error):
      raise ClientError(1, (self.user, self.host))
    else:
      self.sftp = self.ssh.open_sftp()
      try:
        self.sftp.chdir(self.path)
      except IOError:
        raise ClientError(6, (self.path, ))
      else:
        return self.sftp

  def __exit__(self, type, value, traceback):
    if self.sftp:
      self.sftp.close()
      self.sftp = None
    self.ssh.close()
    self.ssh = None

  def upload(self, filename, reader=None, move=False, callback=None,
    force=False):
    """Attempt to upload a file the remote host."""
    if reader and callback:
      raise ValueError('No callback available with reader')
    if not force and filename in self.sftp.listdir():
      raise ClientError(12, (filename, ))
    if not reader:
      try:
        self.sftp.put(filename, filename, callback)
      except OSError:
        raise ClientError(3, (filename, ))
      else:
        if move:
          remove(filename)
    else:
      remote_file = self.sftp.file(filename, 'wb')
      remote_file.set_pipelined(True)
      try:
        while True:
          data = reader.read(32768)
          if not len(data):
            break
          remote_file.write(data)
      finally:
        remote_file.close()

  def download(self, filename, writer=None, move=False, callback=None,
    force=False):
    """Attempt to download a file from the remote host."""
    if writer and callback:
      raise ValueError('No callback available with writer.')
    try:
      if not writer:
        if not force and exists(filename):
          raise ClientError(11, (filename, ))
        self.sftp.get(filename, filename, callback)
      else:
        remote_file = self.sftp.file(filename, 'rb')
        remote_file.prefetch()
        try:
          while True:
            data = remote_file.read(32768)
            if not len(data):
              break
            writer.write(data)
            writer.flush()
        finally:
          remote_file.close()
    except IOError:
      raise ClientError(2, (filename, ))
    except UnicodeDecodeError:
      raise ClientError(7)
    else:
      if move:
        self.sftp.remove(filename)


class ClientConfig(object):

  """Handles loading and saving of options (currently only profiles)."""

  path = environ.get('MYIGLOORC', expanduser(join('~', '.igloorc')))

  def __init__(self):
    try:
      with open(self.path) as handle:
        self.values = load(handle)
    except IOError:
      pass
    self.values.setdefault(
      'host_keys', join(expanduser('~'), '.ssh', 'known_hosts')
    )
    self.values.setdefault('profiles', {})

  def _save(self):
    """Save options to file."""
    with open(self.path, 'w') as handle:
      dump(self.values, handle)

  def _remove(self):
    """Delete options files."""
    remove(self.path)

  def get_url(self, profile):
    """Get URL corresponding to profile."""
    try:
      return self.values['profiles'][profile]
    except KeyError:
      raise ClientError(10, (profile, ))

  def add_url(self, profile, url):
    """Create new profile/URL entry."""
    self.values['profiles'][profile] = url
    self._save()

  def delete_url(self, profile):
    """Delete profile entry."""
    try:
      self.values['profiles'].pop(profile)
    except KeyError:
      raise ClientError(10, (profile, ))
    self._save()

  def show_urls(self):
    """Show all profile/URL entries."""
    return self.values['profiles']

  def get_client(self, url, profile):
    """Get client corresponding to current configuration."""
    url = url or self.get_url(profile)
    return Client(url, self.values['host_keys'])


def config_client(config, arguments):
  """Configure client according to command line arguments."""
  writer = get_stream_writer()
  if arguments['add']:
    config.add_url(
      url=arguments['URL'],
      profile=arguments['PROFILE'] or 'default',
    )
  elif arguments['delete']:
    config.delete_url(arguments['PROFILE'])
  elif arguments['list']:
    write(
      sorted(reversed(config.show_urls().items())),
      writer,
      format='%s [%s]\n'
    )
  else:
    writer.write('%s\n' % (config.path, ))

def run_client(client, arguments):
  """Main handler."""
  writer = get_stream_writer(binary=arguments['--binary'])
  with client as sftp:
    if arguments['--expr']:
      expr = re_compile(
        pattern=arguments['--expr'],
        flags=IGNORECASE if arguments['--case-insensitive'] else 0,
      )
      if arguments['--remote']:
        filenames = sftp.listdir()
      else:
        filenames = listdir('.')
      filenames = [
        filename for filename in filenames
        if (expr.search(filename) and not arguments['--no-match'])
        or (not expr.search(filename) and arguments['--no-match'])
      ]
    else:
      filenames = arguments['FILENAME']
    if arguments['--list']:
      write(filenames, writer)
    else:
      callback = get_callback() if arguments['--track'] else None
      if arguments['--remote']:
        for filename in filenames:
          client.download(
            filename=filename,
            writer=writer if arguments['--stream'] else None,
            move=arguments['--move'],
            force=arguments['--force'],
            callback=callback,
          )
          if not arguments['--stream'] and not arguments['--quiet']:
            writer.write('%s\n' % (filename, ))
      else:
        for filename in filenames:
          client.upload(
            filename=filename,
            reader=stdin if arguments['--stream'] else None,
            move=arguments['--move'],
            force=arguments['--force'],
            callback=callback,
          )
          if not arguments['--stream'] and not arguments['--quiet']:
            writer.write('%s\n' % (filename, ))

def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  try:
    config = ClientConfig()
    if arguments['--config']:
      config_client(config, arguments)
    else:
      client = config.get_client(
        url=arguments['--url'],
        profile=arguments['--profile'],
      )
      run_client(client, arguments)
  except ClientError as err:
    if arguments['--debug']:
      stderr.write(err.traceback)
    else:
      stderr.write('%s\n' % (err.message, ))
    exit(1)


if __name__ == '__main__':
  main()
