dfmon
=====

A GUI for managing SCSI Devices in your Linux system with Truecrypt support.

About
-----

Its creation was motivated by the need to hot-unplug (e)SATA hard disks from the
running system. Recent Linux distributions support this for USB devices but
not for SATA devices directly, afaik (the author). Please tell me, if I'm
wrong, or if this is not supported by the kernel at all.

Device removal preparation follows [a guide from Redhat] [1]. Except for LVM,
md or multipath setups - to keep it simple for the beginning.

[1]: http://www.redhat.com/docs/en-US/Red_Hat_Enterprise_Linux/html/Online_Storage_Reconfiguration_Guide/removing_devices.html

Invokation
----------

The GUI is invoked like so:
	$ python dfmon.py

There is a (very) rudimentary command line interface:
	$ python dfmon.py -c
which does only little more than displaying the system status.

Requirements
------------

* a Python installation
* Qt
* PyQt
* a graphical sudo replacement (kdesu, gksu); 
  otherwise, you should call it with sudo 

On Ubuntu, the necessary dependencies are resolved and installed by:
	$ sudo apt-get install python-qt4

Developed and heavily tested on Kubuntu 8.04 (python 2.5, PyQt 4.3) and
roughly tested on Ubuntu 9.10, OpenSuse 11.
(with more recent version of python and Qt)
Fedora 12 does not work properly because of missing gksu ...

Personal Note
-------------

This tiny project serves also for getting familiar with python itself. Hence,
feel free to point me at problems, give suggestions or provide patches ;)

Copying
-------

Qt dependencies are restricted to dfmonQt. dfmonCmd as well as dfmonBackend
are free of Qt. Therefore, it should be possible to write a different GUI, if
someone dislikes Qt. Additionally, the backend could be licensed 'more free', if
there is interest.

Copyright (c) 2010 by Ingo Bressler

This is Free Software distributed under the terms of the GPL license. See the COPYING file for license rights and limitations.

