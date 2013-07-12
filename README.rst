Igloo
=====

A simple command line SCP client.


Installation
------------

.. code:: bash

  pip install igloo

For ``igloo`` to work, you must have activated key authentication (i.e. you
must be able to ``ssh`` into the remote machine without entering a password or
passphrase).


Examples
--------

The exhaustive list of options can be viewed with ``igloo --help``.

Here are a few common usage patterns (note that each ``--option`` has a shorter
version which can found in the help message):

* Setup the default remote URL:

  .. code:: bash

    $ igloo --config add user@host:path/to/remote/directory

* Copy two files to this remote URL:

  .. code:: bash

    $ igloo first.ext second.log
    first.ext
    second.log

* Download the first file back:

  .. code:: bash

    $ igloo --remote first.ext
    first.ext

* View the list of files in the remote directory that end in ``.log``:

  .. code:: bash

    $ igloo --remote --list --expr='\.log$'
    second.log

* Add a new remote URL corresponding to profile ``public``:

  .. code:: bash

    $ igloo --config add user@host:another/directory/public public

* Transfer all the files in the current directory to the remote ``public`` URL,
  overwriting any preexisting files:

  .. code:: bash

    $ igloo --profile=public --force *
    first.ext
    second.log


* Download all files from the remote directory that don't end in ``.log``, and delete them from the remote
  directory afterwards:

  .. code:: bash

    $ igloo --remote --move --no-match --expr='\.log$'
    first.ext

* View list of profiles:

  .. code:: bash

    $ igloo --config list
    default [user@host:path/to/remote/directory]
    public [user@host:another/directory/public]

* Read from standard input and save remotely as ``hello.log``

  .. code:: bash

    $ echo 'Hello world!' | igloo --stream hello.log
    hello.log


Future work
-----------

* Interactive progress bars (--track)
* Zip files and folders on the fly (--zip)
* Multiple transfers at the same time
