#!/usr/bin/env/ python

"""Tests."""

from getpass import getpass
from igloo import Client, ClientError
from nose import run
from nose.tools import ok_, eq_, raises

HOST = 'orage.in'

class TestIgloo(object):

  def test_connection(self):
    client = Client(HOST)
    with client.get_sftp_client() as sftp:
      pass

  @raises(ClientError)
  def test_connection_with_invalid_user(self):
    client = Client(HOST, user='Foo')
    with client.get_sftp_client() as sftp:
      pass

  @raises(ClientError)
  def test_connection_with_wrong_host_keys(self):
    client = Client(HOST, host_keys='~/')
    with client.get_sftp_client() as sftp:
      pass

  def test_change_directory(self):
    client = Client(HOST)
    with client.get_sftp_client() as sftp:
      sftp.


if __name__ == '__main__':
  run()
