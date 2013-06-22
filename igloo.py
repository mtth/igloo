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
  -b --binary                   Don't decode stdout. This is useful when piping
                                binary files.
  --debug                       Enable full exception traceback.
  -d --download                 Downloading mode.
  -f FOLDER --folder=FOLDER     Folder to copy the file to/from.
  -h --help                     Show this screen.
  --host=HOST                   Remote hostname.
  --list                        List remote files in folder.
  -n NAME --name=NAME           Rename transferred file. Not used if uploading
                                streamed stdin.
  --password                    Use password identification instead of key
                                identification. This is only provided as a
                                convenience and thoroughly untested.
  -p PROFILE --profile=PROFILE  Profile.
  --remove                      Remove remote file.
  -s --stream                   Streaming mode.
  -t --track                    Track transfer progress.
  -u --unzip                    Unzip file after transfer. Raises an error if
                                the transferred file isn't compressed.
  --user=USER                   Username.
  --version                     Show version.
  -z --zip                      Zip file or folder before transfer. Files
                                that are already compressed won't be
                                compressed again. Not yet implemented.

"""

__version__ = '0.0.22'


from codecs import getwriter
from ConfigParser import NoSectionError, SafeConfigParser
from contextlib import contextmanager
from getpass import getpass, getuser
from locale import getpreferredencoding
from os import environ
from os.path import exists, expanduser, join
from socket import error
from sys import stderr, stdin, stdout
from traceback import format_exc
from yaml import load

try:
  from docopt import docopt
  from paramiko import SSHClient, SSHException
except ImportError:
  pass # probably in setup.py


PATH = environ.get('IGLOO_CONFIG_PATH', expanduser(join('~', '.igloorc')))

ERRORS = {
  0: 'something bad happened',
  1: 'unable to connect to %r@%r',
  2: 'remote file %r not found in %r',
  3: 'local file %r not found',
  4: 'transfer interrupted',
  5: 'refusing to transfer directory. try with the --zip option',
  6: 'invalid remote folder %r',
  7: 'unable to decode received data. try with the --binary option',
  8: 'unable to load host keys from file %r',
}


class ClientError(Exception):

  """Base client error class.

  Stores the original traceback to be displayed in debug mode.

  """

  def __init__(self, number, details):
    super(ClientError, self).__init__(ERRORS[number] % details)
    self.number = number
    self.details = details
    self.traceback = format_exc()


class Client(object):

  """API client."""

  @classmethod
  def from_profile(cls, profile, **options):
    """Attempt to load configuration options.

    :param profile: the profile to load
    :param options: options specified on the command line, these will
      override any profile level options.
    :rtype: :class:`Client`

    """
    if profile:
      try:
        parser = SafeConfigParser()
        parser.read(PROFILES_PATH)
        options = dict(parser.items(
          profile,
          vars={k: v for k, v in options.items() if isinstance(v, str)}
        ))
      except (IOError, NoSectionError):
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

  def __init__(self, host, user=None, password=None, host_keys=None):
    self.host = host
    self.user = user or getuser()
    self.host_keys = host_keys or join(expanduser('~'), '.ssh', 'known_hosts')
    self.password = password

  def get_stream_writer(self, writer=stdout, binary=False):
    """Returns the stream writer used by the client."""
    if binary:
      return writer
    else:
      return getwriter(getpreferredencoding())(writer)

  @contextmanager
  def get_sftp_client(self):
    """Attempt to connect via SFTP to the remote host."""
    ssh = SSHClient()
    try:
      ssh.load_host_keys(self.host_keys)
    except IOError:
      raise ClientError(8, (self.host_keys, ))
    try:
      ssh.connect(self.host, username=self.user, password=self.password)
    except (SSHException, error):
      raise ClientError(1, (self.user, self.host))
    else:
      sftp = ssh.open_sftp()
      yield sftp
      sftp.close()
    finally:
      ssh.close()

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

  def upload(self, local_filepath, remote_filepath, track=False, zip_first=False):
    """Attempt to upload a file the remote host."""
    with self.get_sftp_client() as sftp:
      try:
        sftp.chdir(self.folder)
      except IOError:
        raise ClientError(6, (self.folder, ))
      if not stream:
        if track:
          callback = self.get_callback()
        else:
          callback = None
        try:
          sftp.put(filename, new_name or filename, callback)
        except IOError:
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
          writer = self.get_stream_writer(binary)
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
    writer = self.get_stream_writer()
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
      profile=arguments['--profile'] or DEFAULT_PROFILE,
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
      client.upload(
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
