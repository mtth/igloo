#!/usr/bin/env python

"""Igloo: a command line scp client."""

from setuptools import setup

def get_description():
  from igloo import __doc__
  return __doc__

def get_version():
  from igloo import __version__
  return __version__

setup(
    name='igloo',
    version=get_version(),
    description='A command line scp client',
    long_description=get_description(),
    author='Matthieu Monsch',
    author_email='monsch@mit.edu',
    url='http://github.com/mtth/igloo/',
    license='MIT',
    py_modules=['igloo'],
    classifiers=[
      'Development Status :: 4 - Beta',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: MIT License',
      'Programming Language :: Python',
    ],
    install_requires=[
      'docopt',
      'paramiko',
    ],
    entry_points={'console_scripts': ['igloo = igloo:main']},
)
