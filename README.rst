Igloo
=====

A command line pastebin.com_ client. Simple and compelling as can be.


Features
--------

Create pastes:

* from a file (or a list of files):

  .. code:: bash

    $ igloo first.rst second.rst
    Pastebin successfully created! URL: pastebin.com/3A6qX416

* from standard input (great when piping stuff around):

  .. code:: bash

    $ echo 'Hello world!' | igloo 
    Pastebin successfully created! URL: pastebin.com/GREQxa5Z

Download a paste:

.. code:: bash

  $ igloo -d GREQxa5Z
  Hello world!

View your pastes:

.. code:: bash

  $ igloo -l

         key  min pr hit url                       title
    GREQxa5Z    1  1   0 pastebin.com/GREQxa5Z     
    3A6qX416   14  1   0 pastebin.com/3A6qX416     sample
    jfRA2EN3   33  1   2 pastebin.com/jfRA2EN3     summary

Igloo also lets you set syntax highlighting, open your browser to your newest
paste, give a title to your pastes, and more. For a full list of available
options: ``igloo -h``.


Installation
------------

.. code:: bash

  pip install igloo

Before using Igloo, you will also need to create an account on pastebin.com_.


.. _pastebin.com: http://pastebin.com/

