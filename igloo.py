#!/usr/bin/env python

"""Igloo: a command line scp client.

Usage:
  igloo [options] (--list | FILENAME)
  igloo -h | --help | --version

Examples:
  igloo my_file.txt
  igloo -sf private code.py < my_code.py
  echo 'hello world!' | igloo -s hello
  igloo -ds test.log | grep foo

Arguments:
  FILENAME                      The file to copy. If in uploading mode
                                (default) with streaming mode activated this
                                will only be used as remote filename. If in
                                downloading mode, the remote file to fetch.

Options:
  -a --absolute-folder          Absolute remote folder path. Only useful
                                when used with a profile that contains a
                                `root_folder` option.
  -b --binary                   Don't encode stdout. This is useful when piping
                                binary files.
  --debug                       Enable full exception traceback.
  -d --download                 Downloading mode.
  -f FOLDER --folder=FOLDER     Folder to copy the file to/from.
  -h --help                     Show this screen.
  --host=HOST                   Remote hostname.
  --list                        List remote files in folder.
  --password                    Use password identification instead of key
                                identification. This is only provided as a
                                convenience and thoroughly untested.
  -p PROFILE --profile=PROFILE  Profile [default: default].
  -r --recursive                Enable directory transfer. Not yet implemented.
  --remove                      Remove remote file.
  -s --stream                   Streaming mode.
  -t --track                    Track transfer progress.
  --user=USER                   Username.
  --version                     Show version.
  -z --zip                      Zip file or folder before transferring. Files
                                that are already compressed won't be
                                compressed again. Not yet implemented.

"""

__version__ = '0.0.21'


from codecs import getwriter
from ConfigParser import NoSectionError, SafeConfigParser
from contextlib import contextmanager
from getpass import getpass, getuser
from locale import getpreferredencoding
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

  #: Path to configuration file
  config_file = join(expanduser('~'), '.config', 'igloo', 'config')

  @classmethod
  def from_profile(cls, profile, absolute_folder, **options):
    """Attempt to load configuration options.

    :param profile: the profile to load
    :param options: options specified on the command line, these will
      override any profile level options.
    :rtype: :class:`Client`

    """
    try:
      parser = SafeConfigParser()
      parser.read(cls.config_file)
      options = dict(parser.items(
        profile,
        vars={k: v for k, v in options.items() if isinstance(v, str)}
      ))
    except (IOError, NoSectionError):
      if profile != 'default':
        raise ClientError('config loading error')
    if absolute_folder:
      folder = options.get('folder', None)
    else:
      folder = join(
        options.get('root_folder', '.'),
        options.get('folder', None) or options.get('default_folder', '.')
      )
    return cls(
      host=options.get('host', None),
      user=options.get('user', None),
      folder=folder,
      password=options.get('password', None),
    )

  def __init__(self, host, user=None, folder=None, password=None, writer=None):
    self.host = host
    self.user = user or getuser()
    self.folder = folder
    self.password = password
    self.writer = writer or stdout

  def get_writer(self, binary=False):
    if binary:
      return self.writer
    else:
      return getwriter(getpreferredencoding())(self.writer)

  @contextmanager
  def get_sftp_client(self):
    """Attempt to connect via SFTP to the remote host."""
    self.ssh = SSHClient()
    self.ssh.load_host_keys(join(expanduser('~'), '.ssh', 'known_hosts'))
    try:
      self.ssh.connect(self.host, username=self.user, password=self.password)
      try:
        self.sftp = self.ssh.open_sftp()
      except Exception:
        raise ClientError('unable to open sftp connection')
      else:
        try:
          self.sftp.chdir(self.folder)
        except IOError:
          raise ClientError('invalid remote folder %r' % (self.folder, ))
        yield self.sftp
      finally:
        self.sftp.close()
    except Exception as err:
      if isinstance(err, ClientError):
        raise
      else:
        ssh_url = '%s@%s' % (self.user, self.host)
        raise ClientError('unable to connect to %r' % (ssh_url, ))
    finally:
      self.ssh.close()

  def get_callback(self):
    """Callback function for ``sftp.put`` and ``sftp.get``."""
    writer = self.get_writer()
    def callback(transferred, total):
      progress = int(100 * float(transferred) / total)
      if progress < 100:
        writer.write(' %2i%%\r' % (progress, ))
      else:
        writer.write('      \r')
      writer.flush()
    return callback

  def upload(self, filename, track=False, stream=False):
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
          writer = self.get_writer(binary)
          remote_file = sftp.file(filename, 'rb')
          file_size = sftp.stat(filename).st_size
          remote_file.prefetch()
          try:
            size = 0
            while True:
              data = remote_file.read(32768)
              if not len(data):
                break
              writer.write(data)
              size += len(data)
              writer.flush()
          finally:
            remote_file.close()
      except IOError:
        raise ClientError('remote file not found %r' % (filename, ))
      except UnicodeDecodeError:
        raise ClientError('unable to decode file. try with --binary.')

  def remove(self, filename):
    """Attempt to remove a file from the remote host."""
    with self.get_sftp_client() as sftp:
      try:
        sftp.unlink(filename)
      except IOError:
        raise ClientError('remote file not found %r' % (filename, ))

  def list(self):
    """Attempt to list available files on the remote host."""
    writer = self.get_writer()
    with self.get_sftp_client() as sftp:
      filenames = (
        filename
        for filename in sftp.listdir()
        if not filename.startswith(u'.')
      )
      writer.write('\n'.join(filenames))
      writer.write('\n')
      writer.flush()


def main():
  """Command line parser. Docopt is amazing."""
  arguments = docopt(__doc__, version=__version__)
  try:
    client = Client.from_profile(
      profile=arguments['--profile'],
      absolute_folder=arguments['--absolute-folder'],
      host=arguments['--host'],
      user=arguments['--user'],
      folder=arguments['--folder'],
      password=getpass() if arguments['--password'] else None,
    )
    if arguments['--download']:
      client.download(
        filename=arguments['FILENAME'],
        track=arguments['--track'],
        stream=arguments['--stream'],
        binary=arguments['--binary'],
      )
    elif arguments['--list']:
      client.list()
    elif arguments['--remove']:
      client.remove(filename=arguments['FILENAME'])
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
