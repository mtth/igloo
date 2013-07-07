#!/usr/bin/env python

"""Igloo: a command line scp client."""

from setuptools import setup

def get_version():
  from igloo import __version__
  return __version__

setup(
    name='igloo',
    version=get_version(),
    description='A command line SCP client',
    long_description=open('README.rst').read(),
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
      'pyyaml',
    ],
    entry_points={'console_scripts': ['igloo = igloo:main']},
)
