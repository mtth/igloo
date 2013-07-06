#!/usr/bin/env python

"""Igloo: a command line SCP client.

Usage:
  igloo [-bdrs] [-p PROFILE | -u URL] FILENAME ...
  igloo [-abd] [-p PROFILE | -u URL] --list
  igloo -h | --help | --version

Arguments:
  FILENAME                      The file to transfer. If in uploading mode
                                (default) with streaming mode activated this
                                will only be used as remote filename. If in
                                remote mode, the file to fetch.

Options:
  -a --all                      Show/delete all files (including hidden).
  -b --binary                   Don't decode stdout. This is useful when piping
                                binary files.
  -d --debug                    Enable full exception traceback.
  -h --help                     Show this screen.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  -r --remote                   Remote mode.
  -s --stream                   Streaming mode.
  -t --track                    Track progress.
  -u URL --url=URL              Url to SCP to.
  --version                     Show version.

Todo:
  On the fly, zipping/unzipping (-z --zip).
  Clean folder (--clean).
  Make binary option automatic (checking if output is piped).
  Force option that doesn't check if overwriting a file (-f --force).

"""

__version__ = '0.0.23'


from codecs import getwriter
from contextlib import contextmanager
from getpass import getuser
from locale import getpreferredencoding
from os import environ
from os.path import expanduser, join
from socket import error
from sys import stderr, stdin, stdout
from traceback import format_exc

try:
  from docopt import docopt
  from paramiko import SSHClient, SSHException
  from yaml import load
except ImportError:
  pass # probably in setup.py


ERRORS = {
  0: 'something bad happened',
  1: 'unable to connect to %r',
  2: 'remote file %r not found',
  3: 'local file %r not found',
  4: 'transfer interrupted',
  5: 'refusing to transfer directory. try with the --zip option',
  6: 'invalid remote folder %r',
  7: 'unable to decode received data. try with the --binary option',
  8: 'unable to load host keys from file %r',
  9: 'no configuration file found',
  10: 'profile %r not found in configuration file',
}

PATH = environ.get('IGLOO_CONFIG_PATH', expanduser(join('~', '.igloorc')))


def parse_url(url):
  if '@' in url:
    user, url = url.split('@', 1)
  else:
    user = getuser()
  if ':' in url:
    host, path = url.split(':', 1)
  else:
    host = url
    path = '.'
  return user, host, path

class ClientError(Exception):

  """Base client error class.

  Stores the original traceback to be displayed in debug mode.

  """

  def __init__(self, number, details):
    super(ClientError, self).__init__('error: ' + ERRORS[number] % details)
    self.number = number
    self.details = details
    self.traceback = format_exc()


class Client(object):

  """API client."""

  @classmethod
  def from_profile(cls, profile):
    """Attempt to load configuration options.

    :param profile: the profile to load
    :rtype: :class:`Client`

    """
    try:
      with open(PATH) as handle:
        url = load(handle)[profile]
    except IOError:
      raise ClientError(9)
    except KeyError:
      raise ClientError(10, (profile, ))
    return cls(url)

  def __init__(self, url, host_keys=None):
    self.user, self.host, self.path = parse_url(url)
    self.host_keys = host_keys or join(expanduser('~'), '.ssh', 'known_hosts')

  @contextmanager
  def get_sftp_client(self):
    """Attempt to connect via SFTP to the remote host.

    This requires key authentication to be setup.

    """
    ssh = SSHClient()
    try:
      ssh.load_host_keys(self.host_keys)
    except IOError:
      raise ClientError(8, (self.host_keys, ))
    try:
      ssh.connect(self.host, username=self.user)
    except (SSHException, error):
      raise ClientError(1, (self.user, self.host))
    else:
      sftp = ssh.open_sftp()
      try:
        sftp.chdir(self.path)
      except IOError:
        raise ClientError(6, (self.path, ))
      else:
        yield sftp
      finally:
        sftp.close()
    finally:
      ssh.close()

  def get_stream_writer(self, binary=False, writer=stdout):
    """Returns the stream writer used by the client."""
    if binary:
      return writer
    else:
      return getwriter(getpreferredencoding())(writer)

  def get_callback(self):
    """Callback function for ``sftp.put`` and ``sftp.get``."""
    writer = self.get_stream_writer()
    def callback(transferred, total):
      progress = int(100 * float(transferred) / total)
      if progress < 100:
        writer.write(' %2i%%\r' % (progress, ))
      else:
        writer.write('      \r')
      writer.flush()
    return callback

  def upload(self, filename, stream=False, track=False):
    """Attempt to upload a file the remote host."""
    with self.get_sftp_client() as sftp:
      if not stream:
        if track:
          callback = self.get_callback()
        else:
          callback = None
        try:
          sftp.put(filename, filename, callback)
        except OSError:
          raise ClientError(3, (filename, ))
      else:
        remote_file = sftp.file(filename, 'wb')
        remote_file.set_pipelined(True)
        try:
          while True:
            data = stdin.read(32768)
            if not len(data):
              break
            remote_file.write(data)
        finally:
          remote_file.close()

  def download(self, filename, track=False, stream=False, binary=False):
    """Attempt to download a file from the remote host."""
    with self.get_sftp_client() as sftp:
      try:
        if not stream:
          if track:
            callback = self.get_callback()
          else:
            callback = None
          sftp.get(filename, filename, callback)
        else:
          writer = self.get_stream_writer(binary=binary)
          remote_file = sftp.file(filename, 'rb')
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

  def list(self, include_all=False):
    """Attempt to list available files on the remote host."""
    writer = self.get_stream_writer()
    with self.get_sftp_client() as sftp:
      filenames = (
        filename
        for filename in sftp.listdir()
        if not filename.startswith(u'.') or include_all
      )
      writer.write('\n'.join(filenames))
      writer.write('\n')
      writer.flush()


def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  try:
    url = arguments['--url']
    if url:
      client = Client(url)
    else:
      client = Client.from_profile(arguments['--profile'])
    if arguments['--list']:
      client.list(
        include_all=arguments['--all'],
      )
    elif arguments['--remote']:
      for filename in arguments['FILENAME']:
        client.download(
          filename=filename,
          stream=arguments['--stream'],
          binary=arguments['--binary'],
        )
    else:
      for filename in arguments['FILENAME']:
        client.upload(
          filename=filename,
          stream=arguments['--stream'],
        )
  except ClientError as err:
    if arguments['--debug']:
      stderr.write(err.traceback)
    else:
      stderr.write('%s\n' % (err.message, ))
    exit(1)


if __name__ == '__main__':
  main()
