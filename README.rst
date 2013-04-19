Igloo
=====

A command line pastebin client. Simple and compelling as can be.


Features
--------

Create pastes from standard input or a list of files:

.. code:: bash

  $ echo 'Hello world!' | igloo 
  Pastebin successfully created! URL: pastebin.com/GREQxa5Z
  $ igloo first.rst second.rst
  Pastebin successfully created! URL: pastebin.com/3A6qX416

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

For a full list of avaiable options: ``igloo -h``.


Installation
------------

.. code:: bash

  pip install igloo

