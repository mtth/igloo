#!/usr/bin/env python

"""Igloo: a command line SCP client.

Usage:
  igloo [-dflmrq] [-p PROFILE | -u URL] ([-in] -e EXPR | FILENAME ...)
  igloo (-s | --stream) [-bdr] [-p PROFILE | -u URL] FILENAME
  igloo (-c | --config) [add URL [PROFILE] | delete PROFILE | list]
  igloo -h | --help | -v | --version

  For igloo to work, you must have set up key authentication for each host.
  You can then either input each url manually (`-u user@host:remote/path`) or
  save urls you use often to profiles (`-c add user@host:remote/path prof`) and
  then access them directly (`-p prof`). Profiles are saved in $MYIGLOORC or
  $HOME/.igloorc if the former isn't set.

Arguments:
  FILENAME                      A file to transfer. With the `--stream` option,
                                this is only used as remote filename.

Options:
  -b --binary                   Don't decode stdout (by default, stdout is
                                decoded using the local preferred encoding).
  -c --config                   Configuration mode. Use subcommand add to
                                create a new url/profile entry, subcommand
                                delete to delete an entry and subcommand list
                                to display all existing entries. If no
                                subcommand is specified, prints configuration
                                filepath.
  -d --debug                    Enable full exception traceback.
  -e EXPR --expr=EXPR           Regular expression to filter filenames with
                                (e.g. `-e .` will match all files in the
                                directory).
  -f --force                    Allow transferred files to overwrite existing
                                ones (by default, igloo will error out when
                                this happens).
  -h --help                     Show this screen and exit.
  -i --case-insensitive         Case insensitive regular expression matching.
  -l --list                     Show matching filenames and exit without
                                transferring files.
  -m --move                     Delete origin copy after successful transfer.
  -n --no-match                 Inverse match.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  -q --quiet                    No output (by default, the filename of each
                                transferred file is printed to stdout).
  -r --remote                   Remote mode. Filenames will correspond to
                                files on the remote host and all transfers
                                become downloads.
  -s --stream                   Streaming mode. In non-remote mode, the file
                                uploaded will be read from stdin. In remote
                                mode, the downloaded file will be written to
                                stdout.
  -u URL --url=URL              Url to SCP to (will override any profile).
  -v --version                  Show version and exit.

Examples:
  igloo -rle .                  List all files in remote directory.
  igloo -fmq *                  Move all files to remote directory silently.
  igloo -sbr a.zip > b.zip      Download and rename binary file.
  igloo -ine '\.jpe?g$'         Upload all non jpeg files.

"""

__version__ = '0.1.5'


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


class ClientError(Exception):

  """Base client error class.

  Stores the original traceback to be displayed in debug mode.

  """

  def __init__(self, number, details=()):
    super(ClientError, self).__init__('error: ' + ERRORS[number] % details)
    self.traceback = format_exc()


class BaseClient(object):

  """API client."""

  ssh = None
  sftp = None

  def __init__(self, url, host_keys=None):
    self.user, self.host, self.path = parse_url(url)
    self.host_keys = host_keys or join(expanduser('~'), '.ssh', 'known_hosts')

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


class Client(BaseClient):

  """Implements additional convenience methods."""

  config_path = environ.get('MYIGLOORC', expanduser(join('~', '.igloorc')))

  def __init__(self, url=None, profile=None, host_keys=None):
    if not url:
      try:
        url = self.profile[profile]
      except KeyError:
        raise ClientError(10, (profile, ))
    super(Client, self).__init__(url=url, host_keys=host_keys)

  @property
  def profile(self):
    """Dictionary of profiles."""
    try:
      with open(self.config_path) as handle:
        self._profile = load(handle)
    except IOError:
      self._profile = {}
    return self._profile

  def configure(self, profile, url=''):
    """Add and remove profiles."""
    if url:
      self.profile[profile] = url
    else:
      try:
        del self.profile[profile]
      except KeyError:
        raise ClientError(10, (profile, ))
    with open(self.config_path, 'w') as handle:
      dump(self._profile, handle, default_flow_style=False)

  def get_filenames(self, expr, no_match=False, case_insensitive=False,
    recursive=False, remote=False):
    """Return filenames that match a regular expression."""
    regex = re_compile(
      pattern=expr,
      flags=IGNORECASE if case_insensitive else 0,
    )
    if remote:
      if not recursive:
        filenames = sftp.listdir()
      else:
        # TODO
        filenames = []
    else:
      if not recursive:
        filenames = listdir('.')
      else:
        # TODO
        filenames = []
    return [
      filename for filename in filenames
      if (expr.search(filename) and not no_match)
      or (not expr.search(filename) and no_match)
    ]


def configure_client(client, arguments):
  """Configure client according to command line arguments."""
  writer = get_stream_writer()
  if arguments['add'] or arguments['delete']:
    client.configure(
      profile=arguments['PROFILE'] or 'default',
      url=arguments['URL'],
    )
  elif arguments['list']:
    write(
      sorted(reversed(client.profile.items())),
      writer,
      format='%s [%s]\n'
    )
  else:
    write([filename], writer)

def run_client(client, arguments):
  """Main handler."""
  writer = get_stream_writer(binary=arguments['--binary'])
  with client:
    if arguments['--expr']:
      filenames = client.get_filenames(
        expr=arguments['--expr'],
        no_match=arguments['--no-match'],
        case_insensitive=arguments['--case-insensitive'],
        remote=arguments['--remote'],
      )
    else:
      filenames = arguments['FILENAME']
    if arguments['--list']:
      write(filenames, writer)
    else:
      callback = None
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
            write([filename], writer)
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
            write([filename], writer)

def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  try:
    client = Client(
      url=arguments['--url'],
      profile=arguments['--profile'],
    )
    if arguments['--config']:
      configure_client(client, arguments)
    else:
      run_client(client, arguments)
  except ClientError as err:
    if arguments['--debug']:
      stderr.write(err.traceback)
    else:
      stderr.write('%s\n' % (err.message, ))
    exit(1)


if __name__ == '__main__':
  main()
