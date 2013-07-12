#!/usr/bin/env python

"""Igloo: a command line SCP client.

Usage:
  igloo [-adfklmrq] [-p PROFILE | -u URL] ([-inw] -e EXPR | FILEPATH ...)
  igloo (-s | --stream) [-bdr] [-p PROFILE | -u URL] FILEPATH
  igloo (-c | --config) [add URL [PROFILE] | delete PROFILE | list]
  igloo -h | --help | -v | --version

  For igloo to work, you must have set up key authentication for each host.
  You can then either input each url manually (`-u user@host:remote/path`) or
  save urls you use often to profiles (`-c add user@host:remote/path prof`) and
  then access them directly (`-p prof`). Profiles are saved in $MYIGLOORC or
  $HOME/.igloorc if the former isn't set.

Arguments:
  FILEPATH                      Local or remote path of file to transfer. With
                                the `--stream` option, this is only used as
                                remote path. Note that any filepaths
                                corresponding to directories are skipped.

Options:
  -a --ask                      Interactive mode. Ask before transferring each
                                file.
  -b --binary                   Don't decode stdout (by default, stdout is
                                decoded using the local preferred encoding).
  -c --config                   Configuration mode. Use subcommand add to
                                create a new url/profile entry, subcommand
                                delete to delete an entry and subcommand list
                                to display all existing entries. If no
                                subcommand is specified, prints configuration
                                filepath.
  -d --debug                    Enable full exception traceback.
  -e EXPR --expr=EXPR           Regular expression to filter filepaths with
                                (e.g. `-e .` will match all files in the
                                directory).
  -f --force                    Allow transferred files to overwrite existing
                                ones (by default, igloo will error out when
                                this happens).
  -h --help                     Show this screen and exit.
  -i --case-insensitive         Case insensitive regular expression matching.
  -k --keep-hierarchy           Preserve folder hierarchy when transferring
                                files. The default is to transfer files to the
                                current directory.
  -l --list                     Show matching filepaths and exit without
                                transferring files.
  -m --move                     Delete origin copy after successful transfer.
  -n --no-match                 Inverse match.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  -q --quiet                    No output (by default, the filepath of each
                                transferred file is printed to stdout).
  -r --remote                   Remote mode. filepaths will correspond to
                                files on the remote host and all transfers
                                become downloads.
  -s --stream                   Streaming mode. In non-remote mode, the file
                                uploaded will be read from stdin. In remote
                                mode, the downloaded file will be written to
                                stdout.
  -u URL --url=URL              Url to SCP to (will override any profile).
  -v --version                  Show version and exit.
  -w --walk                     Recursive directory exploration.

Examples:
  igloo -rle .                  List all files in remote directory.
  igloo -fmq *                  Move all files to remote directory silently.
  igloo -sbr a.zip > b.zip      Download and rename binary file.
  igloo -ine 'jpe?g$'           Upload all non jpeg files.
  igloo -arwe 'py$'             Download all python files in remote directory
                                hierarchy, asking for confirmation first.

"""

__version__ = '0.1.6'


from codecs import getwriter
from errno import ENOENT, EEXIST
from getpass import getuser
from locale import getpreferredencoding
from os import environ, listdir, mkdir, remove, strerror, walk as os_walk
from os.path import exists, expanduser, isdir, join, sep, split
from re import compile as re_compile, IGNORECASE
from socket import error
from sys import stderr, stdin, stdout
from stat import S_ISDIR
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
  13: 'local file %r already exists',
  14: 'remote file %r already exists',
}


def get_stream_writer(binary=False, writer=stdout):
  """Returns the stream writer used by the client."""
  if binary:
    return writer
  else:
    return getwriter(getpreferredencoding())(writer)

def write(iterable, writer, lazy_flush=False, format='%s\n'):
  """Write to stdout, handles encoding automatically."""
  for elem in iterable:
    writer.write(format % elem)
    if not lazy_flush:
      writer.flush()
  if lazy_flush:
    writer.flush()

def remote_file_exists(path, sftp):
  """Checks if remote file exists."""
  try:
    sftp.stat(path)
  except IOError as err:
    if err.errno == ENOENT:
      return False
    else:
      raise
  else:
    return True

def remote_file_is_directory(path, sftp):
  """Checks if remote path is a directory."""
  return S_ISDIR(sftp.stat(path).st_mode)

def safe_makedirs(path, sftp=None):
  """Recursively create directories."""
  parts = path.split(sep)
  for depth in range(len(parts)):
    part = sep.join(parts[:(depth + 1)])
    if sftp:
      if not remote_file_exists(part, sftp):
        sftp.mkdir(part)
      elif not remote_file_is_directory(part, sftp):
        raise OSError(EEXIST, strerror(EEXIST), path)
    else:
      if not exists(part):
        mkdir(part)
      elif not isdir(part):
        raise OSError(EEXIST, strerror(EEXIST), path)

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

def ask(prompt, default='n'):
  """Simple choice prompter."""
  if default.lower() == 'y':
    defaults = 'Yn'
  else:
    defaults = 'yN'
  choice = raw_input('%s [%s] ' % (prompt, defaults)) or default
  return choice.lower() == 'y'


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

  def transfer(self, remote_filepath, reader=None, writer=None, callback=None):
    """Transfer file. Doesn't check if overwrites."""
    try:
      if reader and not writer:
        # upload
        self.sftp.putfo(reader, remote_filepath, callback=callback)
      elif writer and not reader:
        # download
        self.sftp.getfo(remote_filepath, writer, callback=callback)
      else:
        raise ValueError('Exactly one of reader or writer can be specified.')
    except IOError: # missing remote file
      raise ClientError(2, (remote_filepath, ))
    except UnicodeDecodeError:
      raise ClientError(7)


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
    except IOError as err:
      if err.errno == ENOENT:
        self._profile = {}
      else:
        raise
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

  def get_filepaths(self, expr, no_match=False, case_insensitive=False,
    walk=False, remote=False):
    """Return filepaths that match a regular expression."""
    regex = re_compile(
      pattern=expr,
      flags=IGNORECASE if case_insensitive else 0,
    )
    if walk:
      if remote:
        def walk_directory(path):
          """Walk remote directory."""
          filepaths = []
          for filename in self.sftp.listdir(path):
            filepath = join(path, filename)
            if remote_file_is_directory(filepath, self.sftp):
              filepaths.extend(walk_directory(filepath))
            else:
              filepaths.append(filepath)
          return filepaths
      else:
        def walk_directory(path):
          """Walk local directory."""
          filepaths = []
          for (path, dirnames, names) in os_walk(path):
            filepaths.extend([join(path, filename) for filename in names])
          return filepaths
      # all path start with './', we remove it for consistency
      filepaths = [
        filepath.split(sep, 1)[1]
        for filepath in walk_directory('.')
      ]
    else:
      if remote:
        filepaths = [
          filepath for filepath in self.sftp.listdir()
          if not remote_file_is_directory(filepath, self.sftp)
        ]
      else:
        filepaths = [
          filepath for filepath in listdir('.')
          if not isdir(filepath)
        ]
    return [
      filepath for filepath in filepaths
      if (regex.search(filepath) and not no_match)
      or (not regex.search(filepath) and no_match)
    ]

  def stream(self, remote_filepath, remote=False, binary=False):
    """Stream from stdin / to stdout."""
    if remote:
      self.transfer(
        remote_filepath=remote_filepath,
        writer=get_stream_writer(binary=binary),
      )
    else:
      self.transfer(
        remote_filepath=remote_filepath,
        reader=stdin,
      )

  def download(self, remote_filepath, keep_hierarchy=False, force=False,
    track=False, move=False):
    """Attempt to download a file from the remote host."""
    local_filepath = self._prepare_filepath(
      remote_filepath,
      keep_hierarchy=keep_hierarchy,
      remote=False
    )
    if not force and exists(local_filepath):
      raise ClientError(11, (local_filepath, ))
    if track:
      callback = get_callback()
    else:
      callback = None
    with open(local_filepath, 'wb') as writer:
      self.transfer(
        remote_filepath=remote_filepath,
        writer=writer,
        callback=callback,
      )
    if move:
      self.sftp.remove(remote_filepath)
    return local_filepath

  def upload(self, local_filepath, keep_hierarchy=False, force=False,
    track=False, move=False):
    """Attempt to upload a file the remote host."""
    remote_filepath = self._prepare_filepath(
      local_filepath,
      keep_hierarchy=keep_hierarchy,
      remote=True
    )
    if not force and remote_file_exists(remote_filepath, self.sftp):
      raise ClientError(12, (remote_filepath, ))
    if track:
      callback = get_callback()
    else:
      callback = None
    with open(local_filepath, 'rb') as reader:
      self.transfer(
        remote_filepath=remote_filepath,
        reader=reader,
        callback=callback,
      )
    if move:
      remove(local_filepath)
    return remote_filepath

  def _prepare_filepath(self, filepath, keep_hierarchy=False, remote=False):
    """Returns transferred filepath and creates directories if necessary."""
    try:
      if remote:
        dirname, filename = split(filepath)
        if keep_hierarchy:
          safe_makedirs(dirname, self.sftp)
          new_filepath = filepath
        else:
          new_filepath = filename
      else:
        dirname, filename = split(filepath)
        if keep_hierarchy:
          safe_makedirs(dirname)
          new_filepath = filepath
        else:
          new_filepath = filename
    except OSError as err:
      client_errno = 14 if remote else 13
      raise ClientError(client_errno, (err.filename, ))
    else:
      return new_filepath


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
    write([client.config_path], writer)

def run_client(client, arguments):
  """Main handler."""
  writer = get_stream_writer(binary=arguments['--binary'])
  with client:
    if arguments['--expr']:
      filepaths = client.get_filepaths(
        expr=arguments['--expr'],
        no_match=arguments['--no-match'],
        case_insensitive=arguments['--case-insensitive'],
        remote=arguments['--remote'],
        walk=arguments['--walk'],
      )
    else:
      filepaths = [
        filepath for filepath in arguments['FILEPATH']
        if arguments['--remote'] or not isdir(filepath)
      ]
    if arguments['--list']:
      write(filepaths, writer)
    else:
      remote = arguments['--remote']
      # ask upfront to confirm all filepaths to avoid waiting afterwards
      filepaths = [
        filepath for filepath in filepaths
        if not arguments['--ask'] or ask('Transfer %s?' % (filepath, ))
      ]
      for filepath in filepaths:
        if arguments['--stream']:
          client.stream(
            remote_filepath=filepath,
            remote=remote,
            binary=arguments['--binary'],
          )
        else:
          if remote:
            local_filepath = client.download(
              remote_filepath=filepath,
              move=arguments['--move'],
              keep_hierarchy=arguments['--keep-hierarchy'],
              force=arguments['--force'],
            )
            if not arguments['--quiet']:
              write([local_filepath], writer)
          else:
            remote_filepath = client.upload(
              local_filepath=filepath,
              move=arguments['--move'],
              keep_hierarchy=arguments['--keep-hierarchy'],
              force=arguments['--force'],
            )
            if not arguments['--quiet']:
              write([remote_filepath], writer)

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
