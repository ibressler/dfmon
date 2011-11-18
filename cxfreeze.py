# -*- coding: utf-8 -*-

import platform
from cx_Freeze import setup,Executable

NAME = 'dfmon'
VERSION = '0.2'
BITNESS = platform.architecture()[0]
DISTRIB = platform.linux_distribution()[0].lower()
PATHNAME = NAME+"-"+VERSION+"_"+BITNESS+"_"+DISTRIB
#PATHNAME = NAME+"-"+VERSION+"_"+BITNESS

includefiles = ['COPYING', 'README.md', 'dfmon.sh',
#                'libssl.so.0.9.8',
#                'libcrypto.so.0.9.8'
               ]
includes = [
#    'ssl'
]
excludes = ['Tkinter']

setup(
    name = NAME,
    version = VERSION,
    description = 'Truecrypt enabled mount/umount GUI.',
    author = 'Ingo Breßler',
    author_email = 'dfmon@ingobressler.net',
    options = {'build_exe':
               {'excludes': excludes,
                'include_files': includefiles,
                'build_exe': PATHNAME}
              }, 
    executables = [Executable(script='dfmon.py',
#                              targetDir=PATHNAME,
                              targetName=NAME)]
)

