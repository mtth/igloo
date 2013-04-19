#!/usr/bin/env python

"""
Igloo
=====

A command line pastebin client.

.. code:: bash

  pip install igloo

`Github repo <https://github.com/mtth/igloo>`_

"""

from setuptools import find_packages, setup

def get_version():
  from igloo import __version__
  return __version__

setup(
    name='igloo',
    version=get_version(),
    description='Command line pastebin client',
    long_description=__doc__,
    author='Matthieu Monsch',
    author_email='monsch@mit.edu',
    url='http://github.com/mtth/igloo/',
    license='MIT',
    packages=find_packages(),
    classifiers=[
      'Development Status :: 4 - Beta',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: MIT License',
      'Programming Language :: Python',
    ],
    install_requires=[
      'docopt',
      'requests',
    ],
    entry_points={'console_scripts': ['igloo = igloo:main']},
)
