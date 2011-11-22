# -*- coding: utf-8 -*-
# cxfreeze.py
#
# Copyright (c) 2010-2011, Ingo Breßler <dfmon@ingobressler.net>
#
# This file is part of dfmon.
#
# dfmon is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# dfmon is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with dfmon.  If not, see <http://www.gnu.org/licenses/>.

import platform
from cx_Freeze import setup,Executable

NAME = 'dfmon'
VERSION = '0.2'
BITNESS = platform.architecture()[0]
DISTRIB = platform.linux_distribution()[0].lower()
PATHNAME = NAME+"-"+VERSION+"_"+BITNESS+"_"+DISTRIB

includefiles = ['COPYING', 'README.md',]
includes = []
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
    executables = [Executable(script='bin/dfmon',
                              targetName=NAME)]
)

# vim: set ts=4 sw=4 tw=0:
