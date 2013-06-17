#!/usr/bin/env python

"""Igloo: a command line scp client.

Usage:
  igloo [options] (--list | FILENAME)
  igloo -h | --help | --version

Examples:
  igloo my_file.txt
  igloo -f private < my_code.py
  echo 'hello world!' | igloo -s hello
  igloo -sd test.log | grep foo

Arguments:
  FILENAME                      The file to copy. If in uploading mode
                                (default) with streaming mode activated this
                                will only be used as remote filename. If in
                                downloading mode, the remote file to fetch.

Options:
  --debug                       Enable full exception traceback.
  -d --download                 Downloading mode.
  -f FOLDER --folder=FOLDER     Folder to save/fetch the file to/from.
  -h --help                     Show this screen.
  --host=HOST                   Hostname.
  --http-url=URL                Not used yet.
  --list                        List remote files in folder.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  --remove                      Remove remote file.
  -s --stream                   Streaming mode.
  -t --track                    Track transfer progress.
  --use-password                Use password identification.
  --user=USER                   Username.
  --version                     Show version.

"""

__version__ = '0.0.19'


from ConfigParser import NoSectionError, SafeConfigParser
from contextlib import contextmanager
from getpass import getpass, getuser
from os import fdopen, makedirs, remove
from os.path import exists, expanduser, join
from sys import stderr, stdin, stdout
from traceback import format_exc

try:
  from docopt import docopt
  from paramiko import SSHClient
except ImportError:
  pass # probably in setup.py


class ClientError(Exception):

  """Base client error class.

  Stores the original traceback to be displayed in debug mode.

  """

  def __init__(self, message):
    super(ClientError, self).__init__(message)
    self.traceback = format_exc()


class Client(object):

  """API client."""

  #: Configuration default values
  config_defaults = {
    'user': getuser(),
    'host': '',
    'http_url': '',
    'root_folder': '.',
    'default_folder': '.',
  }

  #: Path to configuration file
  config_file = join(expanduser('~'), '.config', 'igloo', 'config')

  def __init__(self, profile, use_password, **kwargs):
    self.config = self.load_config(
      profile,
      {k: v for k, v in kwargs.items() if not v is None}
    )
    for k, v in self.config_defaults.items():
      self.config.setdefault(k, v)
    self.config['folder'] = join(
      self.config['root_folder'],
      self.config.get('folder', None) or self.config['default_folder'],
    )
    self.use_password = use_password

  @contextmanager
  def get_sftp_client(self):
    """Attempt to connect via SFTP to the remote host."""
    self.ssh = SSHClient()
    self.ssh.load_host_keys(join(expanduser('~'), '.ssh', 'known_hosts'))
    try:
      if self.use_password:
        self.ssh.connect(
          self.config['host'],
          username=self.config['user'],
          password=getpass(),
        )
      else:
        self.ssh.connect(self.config['host'], username=self.config['user'])
      try:
        self.sftp = self.ssh.open_sftp()
      except Exception:
        raise ClientError('unable to open sftp connection')
      else:
        folder = self.config['folder']
        try:
          self.sftp.chdir(folder)
        except IOError:
          raise ClientError('invalid remote folder %r' % (folder, ))
        yield self.sftp
      finally:
        self.sftp.close()
    except Exception as err:
      if isinstance(err, ClientError):
        raise
      else:
        ssh_url = '%s@%s' % (self.config['user'], self.config['host'])
        raise ClientError('unable to connect to ssh url %r' % (ssh_url, ))
    finally:
      self.ssh.close()

  def load_config(self, profile, options):
    """Attempt to load configuration options.

    :param profile: the profile to load
    :param options: options specified on the command line, these will
      override any profile level options.
    :rtype: dict

    """
    try:
      parser = SafeConfigParser()
      parser.read(self.config_file)
      return dict(parser.items(profile, vars=options))
    except (IOError, NoSectionError):
      if profile == 'default':
        return options
      else:
        raise ClientError('config loading error')

  def get_callback(self):
    """Callback function for ``sftp.put`` and ``sftp.get``."""
    def callback(transferred, total):
      progress = 100 * float(transferred) / total
      stdout.write('Progress: %.1f%%\r' % (progress, ))
      stdout.flush()
    return callback

  def upload(self, filename, track, stream):
    """Attempt to upload a file the remote host."""
    with self.get_sftp_client() as sftp:
      if not stream:
        try:
          with open(filename) as handle:
            pass
        except IOError:
          raise ClientError('local file not found %r' % (filename, ))
        if track:
          callback = self.get_callback()
        else:
          callback = None
        sftp.put(filename, filename, callback)
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

  def download(self, filename, track, stream):
    """Attempt to download a file from the remote host."""
    with self.get_sftp_client() as sftp:
      try:
        if not stream:
          if track:
            callback = self.get_callback()
          else:
            callback = None
            sftp.get(filename, filename, callback)
            return filename
        else:
          remote_file = sftp.file(filename, 'rb')
          file_size = sftp.stat(filename).st_size
          remote_file.prefetch()
          try:
            size = 0
            while True:
              data = remote_file.read(32768)
              if not len(data):
                break
              stdout.write(data)
              size += len(data)
              stdout.flush()
          finally:
            remote_file.close()
      except IOError:
        raise ClientError('remote file not found %r' % (filename, ))

  def remove(self, filename):
    """Attempt to remove a file from the remote host."""
    with self.get_sftp_client() as sftp:
      try:
        sftp.unlink(filename)
      except IOError:
        raise ClientError('remote file not found %r' % (filename, ))

  def list(self):
    """Attempt to list available files on the remote host."""
    with self.get_sftp_client() as sftp:
      return [
        filename
        for filename in sftp.listdir()
        if not filename.startswith('.')
      ]


def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  try:
    client = Client(
      profile=arguments['--profile'],
      use_password=arguments['--use-password'],
      user=arguments['--user'],
      host=arguments['--host'],
      folder=arguments['--folder'],
      http_url=arguments['--http-url'],
    )
    if arguments['--download']:
      client.download(
        filename=arguments['FILENAME'],
        track=arguments['--track'],
        stream=arguments['--stream'],
      )
    elif arguments['--list']:
      print '\n'.join(client.list())
    elif arguments['--remove']:
      client.remove(
        filename=arguments['FILENAME'],
      )
    else:
      filename = client.upload(
        filename=arguments['FILENAME'],
        track=arguments['--track'],
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
