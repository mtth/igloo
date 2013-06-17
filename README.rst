Igloo
=====

A simple command line SCP client.


Features
--------

Copy to remote host:

* from a file:

  .. code:: bash

    $ igloo first.rst

* from standard input (great when piping stuff around):

  .. code:: bash

    $ echo 'Hello world!' | igloo -s hello.txt

Copy from remote host:

.. code:: bash

  $ igloo -d hello.txt
  Hello world!

For the list of all options: ``igloo -h``.


Installation
------------

.. code:: bash

  pip install igloo
