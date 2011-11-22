# -*- coding: utf-8 -*-
# uicmd.py
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

"""Commandline interface for dfmon (rudimentary).
"""

import time
import backend
from backend import MyError, DeviceInUseWarning, removeLineBreak, formatSize

def inUseStr(isInUse):
    if isInUse:
        return "[used]"
    else:
        return "[    ]"

def formatBlkDev(blkDev, lvl, prefix):
    if not blkDev:
        return []
    line = []
    # add recursion depth dependent prefix
    o = ""
    for dummy in range(0, lvl):
        o = o + " "
    # add the description of a single device
    o = o + prefix + blkDev.ioFile()
    line.append(o) # first column
    # add usage status
    line.append(inUseStr(blkDev.inUse()))
    line.append(blkDev.mountPoint())
    line.append(formatSize(blkDev.size())) # last column
    res = []
    res.append(line) # output is list of lines (which are column lists)
    # add sub devices recursive
    lvl = lvl + len(prefix)
    for part in blkDev.partitions():
        res.extend(formatBlkDev(part, lvl, prefix))
    for holder in blkDev.holders():
        res.extend(formatBlkDev(holder, lvl, prefix))
    lvl = lvl - len(prefix)
    return res

def printTable(listArr):
    """Prints a table with optimal column width. 
    Input is a list of rows which are lists of strings"""
    colWidth = []
    # determine optimal width of each column
    for col in range(0, len(listArr[0])):
        maxWidth = 0
        for row in range(0, len(listArr)):
            width = len(listArr[row][col])
            if width > maxWidth:
                maxWidth = width
        colWidth.append(maxWidth)
    o = ""
    for row in listArr:
        if len(o) > 0:
            o = o + "\n"
        for col, width in zip(row, colWidth)[:-1]:
            o = o + "%-*s " % ( width, col )
        o = o + "%*s " % ( colWidth[-1], row[-1] )

    return o

def printBlkDev(blkDev):
    return printTable(formatBlkDev(blkDev, 1, "'> "))

def getStatus():
    devList = backend.STATUS.getDevices()
    i = 0
    for dev in devList:
        out = "("+str(i) + ")\t"
        out = out + dev.model() + "\t"
        out = out + inUseStr(dev.inUse()) + "\t"
        out = out + dev.scsiStr()
        if i > 0:
            out = "\n" + out
            for dummy in range(0, len(out)):
                out = "-" + out
        print out
        print printBlkDev(dev.blk())
        i = i + 1

    return devList

def consoleMenu():
    try:
        devList = getStatus()
    except MyError, e:
        print "Error initializing system status: ", e
    else:
        intext = removeLineBreak(
            raw_input("\n=> Select a device ('q' for quit): "))
        if intext != "q" and intext.isdigit():
            d = int(intext)
            if d < 0:
                d = 0
            if d >= len(devList):
                d = len(devList)
            print ("selected device: {0}\n{1}"
                   .format(intext, printBlkDev(devList[d].blk())))
            try:
                devList[d].blk().mount()
            except DeviceInUseWarning:
                intext = removeLineBreak(
                    raw_input("\n=> Selected device is in use, "+
                              "unmount ? [Yn] "))
                if len(intext) == 0:
                    devList[d].blk().umount()
        else:
            print "aborted."
    
        time.sleep(1.0)
        getStatus()
        return 0

# vim: set ts=4 sw=4 tw=0:
