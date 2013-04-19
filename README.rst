Igloo
=====

A command line pastebin client.

Simple and compelling as can be.

Create a pastebin from standard input or a file:

.. code:: bash

  $ igloo sample.txt
  Pastebin successfully created! URL: pastebin.com/3A6qX416
  $ echo 'Hello world!' | igloo 
  Pastebin successfully created! URL: pastebin.com/GREQxa5Z

Download a pastebin:

.. code:: bash

  $ igloo -d GREQxa5Z
  Hello world!

View your pastebins:

.. code:: bash

  $ igloo -l
  3 existing pastes found:

         key  min pr hit url                       title
    GREQxa5Z    1  1   0 pastebin.com/GREQxa5Z     
    3A6qX416   14  1   0 pastebin.com/3A6qX416     sample
    jfRA2EN3   33  1   2 pastebin.com/jfRA2EN3     summary

