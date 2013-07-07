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

The exhaustive list of options can be viewed with ``igloo --help``. Rather than
go over these again, below are a few common usage patterns (each time we
include the short version):

* Setup the default remote URL:

  .. code:: bash

    $ igloo --config add user@host:path/to/remote/directory
    $ igloo -c add user@host:path/to/remote/directory

* Copy a file to this remote URL:

  .. code:: bash

    $ igloo file.ext

* Download back the file:

  .. code:: bash

    $ igloo --remote file.ext
    $ igloo -r file.ext

* View the list of files in the remote directory that have end in ``.ext``:

  .. code:: bash

    $ igloo --remote --list --expr='\.ext$'
    $ igloo -rle '\.ext$'

* Add a new remote URL corresponding to profile ``public``:

  .. code:: bash

    $ igloo --config add user@host:another/directory/public public
    $ igloo -c add user@host:another/directory/public public

* Transfer all the files in the current directory to the remote ``public`` URL,
  overwriting any preexisting files:

  .. code:: bash

    $ igloo --profile=public --force *
    $ igloo -fp public *


* Download all files from the remote directory, and delete them from the remote
  directory afterwards:

  .. code:: bash

    $ igloo --remote --move --expr=.
    $ igloo -rme .

* View list of profiles:

  .. code:: bash

    $ igloo --config list

* Read from standard input and save remotely as ``hello.log``

  .. code:: bash

    $ echo 'Hello world!' | igloo --stream hello.log
