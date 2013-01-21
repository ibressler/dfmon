# -*- coding: utf-8 -*-
# backend.py
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

"""dfmon backend intelligence

Device removal procedure follows recommendations at:
http://docs.redhat.com/docs/en-US/Red_Hat_Enterprise_Linux/5/html/Online_Storage_Reconfiguration_Guide/removing_devices.html
But it does not yet support LVM, md or multipath setups (usually not used
in desktop scenarios).
"""

import sys
import os
import glob
import stat
import subprocess
import time
import logging

# required system paths
OS_DEV_PATH = "/dev/"
OS_SYS_PATH = "/sys/class/scsi_device/"

# graphical sudo handlers to test for, last one is the fallback solution
PLAIN_SUDO_QUESTION = "askforpwd"
KNOWN_SUDO_HANDLERS = [["kdesu", "-c"],
                     ["gksudo", "--"],
                     ["sudo", "-p", PLAIN_SUDO_QUESTION, "-s"],
                     ["su", "-c"]]

# were does this come from, how to determine this value ?
BLOCKSIZE = long(512)

# we support disks and cdrom/dvd drives
SUPPORTED_DEVICE_TYPES = [0, 5]

# size/capacity formatting data
MAGNITUDE = long(1024)
SIZES_NAMES = ["P", "T", "G", "M", "K", "B"]
SIZES_VALUES = [pow(MAGNITUDE, i)
                for i in reversed(range(0, len(SIZES_NAMES)))]

# time formatting data, based on seconds
TIME_NAMES = ["y", "w", "d", "h", "m", "s"]
TIME_VALUES = [31536000, 604800, 86400, 3600, 60, 1]

# output indent level used for console output
OUTPUT_INDENT = ""

## implementation ##

def formatSize(size):
    """
    Formats the given number to human readable size information in bytes
    """
    if not size or size < 0:
        return "-1"
    for v, n in zip(SIZES_VALUES, SIZES_NAMES):
        short = float(size) / float(v)
        if short >= 1.0:
            return "%.2f%s" % (short, n)
    else:
        return "%.2f%s" % (short, n)

def formatTimeDistance(t):
    if not t:
        return "-1"
    if t < 0:
        t = abs(t)
    s = ""
    for v, n in zip(TIME_VALUES, TIME_NAMES):
        if len(s) > 0:
            s += " "
        if t > v:
            factor = int(t/v)
            s += "%d%s" % (factor, n)
            t -= factor * v
    return s

def strInList(searchStr):
    return lambda line: line.find(searchStr) >= 0

def removeLineBreak(text):
    return text.strip(" \r\t\n")

def getLineFromFile(filename):
    """
    Reads a single line (first one) from a file with the specified name.
    """
    if not os.path.isfile(filename):
        return ""
    fd = open(filename, 'r')
    text = removeLineBreak(fd.readline())
    fd.close()
    return text

class MyError(StandardError):
    def __init__(self, msg = ""):
        StandardError.__init__(self)
        self.msg = msg
    def __str__(self):
        return str(self.msg)
    def __repr__(self):
        return repr(self.msg)

class CmdReturnCodeError(StandardError):
    def __init__(self, cmdList = None, returnCode = 0, stderr = ""):
        StandardError.__init__(self)
        self.cmdList = cmdList
        self.returnCode = returnCode
        self.stderr = stderr
    def __str__(self):
        return ("CmdReturnCodeError: "+str(self.returnCode)+"\n"
                +" ".join(self.cmdList)+"\n"
                +self.stderr)

class DeviceInUseWarning(UserWarning):
    pass

class DeviceHasPartitionsWarning(UserWarning):
    pass

class RemovalSuccessInfo(Exception):
    pass

class SysCmd:
    _cmd = None # Popen object of the last command called
    _cmdList = None # command string list of the last command
    _cmdStatus = None # exit status of the recently invoked command
    _sudo = None
    
    def __init__(self, cmdList, sudo = False):
        """
        Calls a system command in a subprocess asynchronously.
        Does not block. Raises an exception if the command was not found.
        """
        self._sudo = False
        if not cmdList or len(cmdList) <= 0:
            raise MyError("No command supplied!")
        if sudo:
            newcmd = STATUS.sudoHandler()[1:] # omit command name
            if "-c" in newcmd[-1]: # 'su -c' needs cmd as single string
                newcmd.append(" ".join(cmdList))
            else:
                newcmd.extend(cmdList)
            cmdList = newcmd
            self._sudo = True
        try:
            #print "starting:", cmdList
            self._cmd = subprocess.Popen(cmdList,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE)
        except Exception, e:
            raise MyError("Failed to run command: \n'"+
                                    " ".join(cmdList)+"': \n"+str(e))
        else:
            self._cmdList = cmdList
            self._cmdStatus = self._cmd.poll()

    def cmdFinished(self):
        if not self._cmd or self._cmd.poll() != None:
            return True
        else:
            return False

    def cmdStatusChanged(self):
        if self._cmdStatus != self._cmd.poll():
            self._cmdStatus = self._cmd.poll()
            return True
        else: # nothing changed
            return False

    def output(self):
        """Blocks until the last command finished.
        On success, returns a list of output lines.
        Raises an exception if the return code of the last command is not 0.
        """
        if not self._cmd: 
            return []
        stdout = []
        stderr = []
        while not self.cmdFinished():
            if self._cmd.stderr:
                err = self._cmd.stderr.read(len(PLAIN_SUDO_QUESTION)).strip()
                if (self._sudo and
                    STATUS.sudoHandler()[0] == "sudo" and
                    err == PLAIN_SUDO_QUESTION):
                    # catch and handle sudo pwd question
                    if STATUS.sudoPwdFct:
                        self._cmd.stdin.write(STATUS.sudoPwdFct()+"\n")
                    else:
                        self._cmd.stdin.write("\n")
                else:
                    err += self._cmd.stderr.readline()
                stderr.append(err) # preserve possible error msgs
            time.sleep(0.1) # wait some time for the command to finish
        self.cmdStatusChanged()
        returncode = self._cmd.poll()
        if self._cmd.stderr:
            stderr.extend(self._cmd.stderr.readlines())
        if returncode != None and returncode != 0:
            raise CmdReturnCodeError(self._cmdList,
                                     returncode, "\n".join(stderr))
        # no error
        if self._cmd.stdout:
            stdout.extend(self._cmd.stdout.readlines())
        return stdout

class Status:
    """
    Retrieves system status regarding Scsi, associated block devices
    and mountpoints.
    """
    _mountStatus = None
    _swapStatus = None
    _devStatus = None # simple list of scsi device names available
    _devList = None # list of devices
    _sudo = None # sudo handler for the current system
    sudoPwdFct = None # The function to call when a sudo password is
                      # required. It has to return a string.

    def __init__(self):
        if sys.platform != "linux2":
            raise MyError("This tool supports Linux only (yet).")
        for path in OS_DEV_PATH, OS_SYS_PATH:
            if not os.path.isdir(path):
                raise MyError("Specified device path '{0}' does not exist !"
                              .format(path))

    def sudoHandler(self):
        if not self._sudo or len(self._sudo) == 0:
            self._sudo = None
            for handler in KNOWN_SUDO_HANDLERS:
                for path in os.environ["PATH"].split(":"):
                    handlerPath = os.path.join(path, handler[0])
                    if not os.path.isfile(handlerPath):
                        continue
                    # keep the plain command name, add the full path
                    self._sudo = handler[1:] # arguments
                    self._sudo[:0] = [handler[0], handlerPath] # prepend
                    if self._sudoHandlerWorks():
                        break
                if self._sudoHandlerWorks():
                    break
        if not self._sudo or len(self._sudo) == 0:
            raise MyError("No sudo handler found: "+str(KNOWN_SUDO_HANDLERS))
        else:
            return self._sudo

    def _sudoHandlerWorks(self):
        if self._sudo is None:
            return False
        try:
            text = "sudotest"
            cmd = SysCmd(["echo -n {0}".format(text)], sudo=True)
            if cmd.output()[0] != text:
                raise StandardError
        except StandardError:
            self._sudo = None
            return False
        else:
            return True

    def update(self):
        self.devStatusChanged()
        self.mountStatusChanged()
        self._swapStatus = SwapStatus()
        self._devList = getScsiDevices(OS_SYS_PATH)

    def devStatusChanged(self):
        devStatus = [os.path.basename(p)
                     for p in glob.glob(OS_SYS_PATH+os.sep+"*")]
        if not self._devStatus or len(self._devStatus) != len(devStatus):
            self._devStatus = devStatus
            return True
        # compare lists, same length
        for d in self._devStatus:
            if not d in devStatus:
                self._devStatus = devStatus
                return True
        return False

    def mountStatusChanged(self):
        mountStatus = MountStatus()
        if not self._mountStatus or self._mountStatus != mountStatus:
            self._mountStatus = mountStatus
            return True
        return False

    def getDevices(self):
        self.update()
        return self._devList

    def swap(self):
        return self._swapStatus

    def mount(self):
        return self._mountStatus

class SwapStatus:
    """
    Summary of active swap partitions or devices
    """

    _swapData = None
    _devices = None

    def __init__(self):
        """Returns the output of the 'swapon -s' command, line by line"""
        cmd = SysCmd(["/sbin/swapon","-s"])
        self._swapData = cmd.output()
        # get a list of swap devices
        self._devices = []
        for line in self._swapData:
            lineList = line.replace("\t"," ").split()
            if lineList[1] != "partition":
                continue
            self._devices.append(lineList[0])

    def isSwapDev(self, ioFile):
        if not self._devices or len(self._devices) < 1:
            return False
        resList = filter(strInList(ioFile), self._devices)
        if resList and len(resList) > 0:
            return True
        else:
            return False

class MountStatus:
    """Status of all the filesystems mounted in the system"""

    _mountData = None

    def __init__(self):
        """Returns the output of the 'mount' command, line by line"""
        cmd = SysCmd(["mount"])
        self._mountData = cmd.output()

    def __eq__(self, other):
        return "".join(self._mountData) == "".join(other.data())

    def __ne__(self, other):
        return not self.__eq__(other)

    def data(self):
        return self._mountData

    def getMountPoint(self, ioFile):
        if not self._mountData or len(self._mountData) < 1:
            return ""
        resList = filter(strInList(ioFile+" "), self._mountData)
        mountPoint = ""
        if resList and len(resList) > 0:
            mountPoint = resList[0].split("on")[1]
            mountPoint = mountPoint.split("type")[0]
            mountPoint = removeLineBreak(mountPoint)
        else:
            global STATUS
            if STATUS.swap().isSwapDev(ioFile):
                mountPoint = "swap"
        return mountPoint

class Device:
    _sysfsPath = None # path to the device descriptor in /sys/

    def __init__(self, path = ""):
        path = os.path.realpath(path)
        self.setSysfs(path)

    def sysfs(self):
        return self._sysfsPath

    def setSysfs(self, path):
        if not os.path.isdir(path):
            raise MyError("Device path does not exist: "+path)
        self._sysfsPath = path

    def isBlock(self):
        """Returns True if the Device is a BlockDevice."""
        return False

    def isScsi(self):
        """Returns True if the Device is a ScsiDevice."""
        return False

    def shortName(self):
        """Returns the short device name for GUI display."""
        return ""

    def fullName(self):
        """Returns the complete device name for informative uses."""
        return ""

class BlockDevice(Device):
    _devName = None
    _ioFiles = None
    _devNum = None
    _size = None
    _partitions = None # list of BlockDevices
    _holders = None    # list of BlockDevices
    _mountPoint = None
    _timeStamp = None

    # getter methods

    def shortName(self):
        return os.path.basename(self.fullName())

    def fullName(self):
        fn = ""
        if len(self.ioFiles()) > 0:
            fn = self.ioFiles()[0]
        return fn

    def ioFiles(self): 
        """
        Returns the absolute filename of the block device file
        (usually in /dev/).
        """
        if not self._ioFiles:
            return []
        return self._ioFiles

    def mountPoint(self): 
        """
        Returns the absolute path where this device is mounted.
        Empty if unmounted.
        """
        if not self._mountPoint:
            return ""
        return self._mountPoint

    def size(self): 
        """Returns the block devices size in bytes."""
        if not self._size:
            return -1
        return self._size

    def partitions(self): 
        """Returns the partitions as list of BlockDevices"""
        if not self._partitions:
            return []
        return self._partitions

    def holders(self): 
        """Returns the holders as list of BlockDevices"""
        if not self._holders:
            return []
        return self._holders

    def isBlock(self):
        return True

    def __init__(self, sysfsPath, blkDevName):
        Device.__init__(self, sysfsPath)
        self.setSysfs(self.sysfs() + os.sep)
        self._devName = blkDevName
        self._size = getSize(sysfsPath)
        if self._size < 0:
            raise MyError("Could not determine block device size")
        self.getDeviceNumber()
        self._ioFiles = DEVICE_FILE_CACHE.getDeviceFiles(self._devNum)
        for fn in self._ioFiles:
            if not os.path.exists(fn):
                raise MyError("Could not find IO device path '{0}'".format(fn))
        self.timeStamp()
        self.update()
        # final verification
        if not self.isValid():
            raise MyError("Determined block device information not valid")

    def update(self):
        # determine mount point
        self._mountPoint = None
        for fn in self._ioFiles:
            self._mountPoint = STATUS.mount().getMountPoint(fn)
            if (self._mountPoint == "swap" or
                os.path.isdir(self._mountPoint)):
                break
        # get partitions eventually
        self._partitions = self.getSubDevices(self.sysfs(), self._devName+"*")
        # get holders eventually
        basePath = self.sysfs()+"holders"+os.sep
        self._holders = self.getSubDevices(basePath, "*")

    def getSubDevices(self, basePath, matchStr):
        """
        Returns a list of sub-devices (partitions and holders/dependents)
        """
        if not self.isValid():
            return []
        entries = glob.glob(basePath + matchStr)
        if entries is None or len(entries) <= 0:
            return []
        # return a list of the holder names relative to the input block path
        relativeNames = [path[len(basePath):] for path in entries]
        # add all partitions as block devices (recursive)
        deviceList = []
        for devName in relativeNames:
            queryPath = os.path.join(basePath, devName)
            if not os.path.isdir(queryPath):
                continue
            blockDev = BlockDevice(queryPath, devName)
            if not blockDev.isValid():
                raise MyError("Not Valid")
            deviceList.append(blockDev)
        return deviceList

    def inUse(self):
        if self._holders and len(self._holders) > 0:
            for h in self._holders:
                if h.inUse():
                    return True
        if self._partitions and len(self._partitions) > 0:
            for p in self._partitions:
                if p.inUse():
                    return True
        if self._mountPoint:
            return True
        return False

    def __str__(self):
        res = ""
        for attr in [self._devName, self._ioFiles, self._mountPoint, 
                     formatSize(self._size), self._devNum, self.sysfs()]:
            res = res + str(attr) + " "

        global OUTPUT_INDENT
        OUTPUT_INDENT = OUTPUT_INDENT + "  "
        prefix = "\n" + OUTPUT_INDENT
        if self._holders:
            res = res + prefix + "[holders:]"
            for h in self._holders:
                res = res + prefix + str(h)
        elif self._partitions:
            res = res + prefix + "[partitions:]"
            for p in self._partitions:
                res = res + prefix + str(p)
        else:
            pass

        OUTPUT_INDENT = OUTPUT_INDENT[:-2]

        return res

    def isValid(self):
        return self._devName and \
                os.path.isdir(self.sysfs()) and \
                all([os.path.exists(fn) for fn in self._ioFiles]) and \
                self._devNum > 0 and \
                self._size >= 0

    def timeStamp(self):
        """Get the time this device was added to the system."""
        if not self._timeStamp:
            if not any([os.path.exists(fn) for fn in self.ioFiles()]):
                self._timeStamp = -1
            else:
                try:
                    statinfo = os.stat(self.ioFiles()[0])
                except Exception, e:
                    self._timeStamp = -1
                else:
                    mtime = statinfo[stat.ST_MTIME]
                    atime = statinfo[stat.ST_ATIME]
                    ctime = statinfo[stat.ST_CTIME]
                    self._timeStamp = mtime
                    # get the oldest timestamp
                    if atime < self._timeStamp:
                        self._timeStamp = atime
                    if ctime < self._timeStamp:
                        self._timeStamp = ctime
        return self._timeStamp

    def getDeviceNumber(self):
        if not self._devNum:
            fn = os.path.join(self.sysfs(), "dev")
            if not os.path.isfile(fn):
                return -1
            (major, minor) = getLineFromFile(fn).split(":")
            if not major or not minor or major < 0 or minor < 0:
                return -1
            self._devNum = os.makedev(int(major), int(minor))
        return self._devNum

    def mount(self, password = None):
        """Mount block device"""
        # no partitions
        if len(self._partitions) == 0:
            if not any([os.path.exists(fn) for fn in self.ioFiles()]):
                return
            if self.inUse():
                raise DeviceInUseWarning()
            else:
                try:
                    if password is not None:
                        cmd = SysCmd(["truecrypt", "-t",
                                      "--non-interactive",
                                      "-p", password,
                                      "--mount", self.ioFiles()[0]],
                                     sudo = True)
                    else:
                        cmd = SysCmd(["truecrypt", "--mount",
                                      self.ioFiles()[0]], sudo = True)
                    cmd.output()
                except MyError, e:
                    raise MyError("Failed to mount '{0}':\n{1}"
                                  .format(self.ioFiles()[0], str(e)))
        elif len(self._partitions) == 1:
            self._partitions[0].mount()
        else:
            raise DeviceHasPartitionsWarning()
        self.update()

    def umount(self):
        """Unmount block device"""
        for part in self._partitions:
            part.umount()
        for holder in self._holders:
            holder.umount()
        if not os.path.isdir(self.mountPoint()):
            return
        # function tests for truecrypt device files
        isTruecrypt = strInList("truecrypt")
        try:
            cmd = None
            if any([isTruecrypt(fn) for fn in self._ioFiles]):
                # --non-interactive
                cmd = SysCmd(["truecrypt", "-t",
                              "--non-interactive",
                              "-d", self.mountPoint()], True)
            else:
                cmd = SysCmd(["umount", self.mountPoint()], True)
            stdout = "".join(cmd.output())
            if len(stdout) > 0 and stdout != "passprompt":
                raise MyError(stdout)
        except MyError, e:
            raise MyError("Failed to umount '{0}':\n{1}"
                          .format(self.ioFiles()[0], str(e)))
        self.update()

    def flush(self):
        """Flushes the device buffers."""
        for part in self._partitions:
            part.flush()
        for holder in self._holders:
            holder.flush()
        if self.inUse() or not os.path.exists(self.ioFiles()[0]):
            return
        try:
            cmd = SysCmd(["/sbin/blockdev",
                          "--flushbufs", self.ioFiles()[0]], True)
            cmd.output()
        except CmdReturnCodeError, e:
            # what to do on fail, ignore ?
            raise MyError(str(e))

def getSize(sysfsPath):
    """
    Returns the overall numerical size of a block device.

    arg: absolute path to the block device descriptor
    """
    if not os.path.isdir(sysfsPath):
        return -1
    fn = os.path.join(sysfsPath, "size")
    text = getLineFromFile(fn)
    if text.isdigit():
        return long(text)*BLOCKSIZE
    else:
        return -1

class ScsiDevice(Device):
    _scsiAdr = None # list with <host> <channel> <id> <lun>
    _dev = None     # associated Block device object
    _driverName = None
    _vendor = None
    _model = None

    # getter methods

    def shortName(self):
        return self.scsiStr()

    def fullName(self):
        return self.scsiStr()+" "+self.model()

    def blk(self): 
        """Returns the associated BlockDevice."""
        return self._dev

    def scsiStr(self): 
        """Returns the SCSI address of this device as string."""
        if not self._scsiAdr:
            return ""
        return "["+reduce(lambda a, b: a+":"+b, self._scsiAdr)+"]"

    def isScsi(self):
        return True

    def inUse(self): 
        """
        Tells if this device is in use somehow (has mounted partitions).
        """
        return self._dev.inUse()

    def mount(self):
        return self._dev.mount()

    def umount(self):
        return self._dev.umount()

    def flush(self):
        return self._dev.flush()

    def __init__(self, path, scsiStr):
        Device.__init__(self, os.path.join(path, scsiStr, "device"))
        self._scsiAdr = scsiStr.split(":")
        if not self.isSupported():
            # throw exception here
            raise MyError("Device type not supported")
        path, name = getBlkDevPath(self.sysfs())
        if not name or not path:
            # throw exception
            raise MyError("Could not determine block device path in /sys/")
        self._dev = BlockDevice(path, name)
        self.driver()
        self.vendor()
        self.model()
        self.timeStamp()
        # final verification
        if not self.isValid():
            raise MyError("Determined Scsi device information not valid")

    def model(self):
        if self._model and len(self._model) > 0:
            return self._model
        self._model = ""
        fn = os.path.join(self.sysfs(),"model")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                self._model = txt
        return self._model

    def vendor(self):
        if self._vendor and len(self._vendor) > 0:
            return self._vendor
        self._vendor = ""
        fn = os.path.join(self.sysfs(),"vendor")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                self._vendor = txt
        return self._vendor

    def driver(self):
        if self._driverName and len(self._driverName) > 0:
            return self._driverName
        sysfsPath = self._dev.sysfs()
        if not os.path.isdir(sysfsPath):
            return ""
        path = os.path.realpath(os.path.join(sysfsPath,"device"))
        path, tail = os.path.split(path)
        path, tail = os.path.split(path)
        path, tail = os.path.split(path)
        path = os.path.realpath(os.path.join(path,"driver"))
        path, tail = os.path.split(path)
        self._driverName = tail
        return self._driverName

    def timeStamp(self):
        """Get the time this device was added to the system."""
        return self.blk().timeStamp()

    def isSupported(self):
        fn = os.path.join(self.sysfs(),"type")
        if not os.path.isfile(fn): 
            return False
        txt = getLineFromFile(fn)
        if not txt.isdigit():
            return False
        devtype = int(txt)
        for t in SUPPORTED_DEVICE_TYPES:
            if devtype == t:
                return True
        else:
            return False

    def isValid(self):
        return (len(self._scsiAdr) == 4 and
                self.sysfs() and os.path.isdir(self.sysfs()) and
                self._dev.isValid())
        # test for every blk device being valid

    def remove(self):
        if self.inUse():
            self.umount()
        ts = time.time()
        # wait a sec
        while self.inUse() and time.time() < ts+1.5:
            time.sleep(0.1)
        # still in use
        if self.inUse():
            raise MyError("Could not umount this device!")
        else:
            # not in use anymore, remove the device
            delPath = os.path.join(self.sysfs(), "delete")
            if not os.path.isfile(delPath):
                raise MyError("Could not find '"+delPath+"'")
            else:
                self._dev.flush()
                try:
                    cmd = SysCmd(["sh -c 'echo 1 > "+delPath+"'"], True)
                    cmd.output()
                except CmdReturnCodeError, e:
                    raise MyError(str(e))
                else:
                    time.sleep(0.1)
                    if not self.isValid():
                        raise RemovalSuccessInfo()

    def __str__(self):
        """Outputs full detailed information about this devices"""
        if not self.isValid():
            return "not valid!"
        output = (str(self._scsiAdr) +
                ", in use: " + str(self._dev.inUse()) +
                ", driver: " + str(self._driverName) +
                ", vendor: " + str(self._vendor) +
                ", model: " + str(self._model) +
                "\n" + str(self._dev))
        return output

def getBlkDevPath(devPath):
    """
    Returns the scsi block device path.

    in: path to the scsi device
    out: path to the associated block device AND the block device name
    """
    if not os.path.isdir(devPath):
        return ("", "")
    # old style
    devPath = os.path.join(devPath, "block")
    entries = glob.glob(devPath+":*")
    if not entries:
        # new style
        entries = glob.glob(devPath+os.sep+"*")
    if not entries: # still not found
        return ("", "")
    fullPath = entries[0]
    devName = fullPath[len(devPath)+1:]
    return (fullPath, devName)

class DeviceFileCache(object):
# how to improve this ? is there a direct way to get the device file ?
# speedup by caching ?
    _cache = None

    def __init__(self):
        self._cache = dict()
        self.rebuild()

    def getDeviceFiles(self, devnum):
        """
        Search the block device filename in /dev/ based on the major/minor
        number.
        """
        # retrieve the io file if available
        if devnum not in self._cache:
            self.rebuild()
        names = self._cache.get(devnum, [])
        return names

    def rebuild(self):
        self._cache.clear()
        for root, dirs, files in os.walk(OS_DEV_PATH):
            # ignore directories with leading dot
            for i in reversed(range(0, len(dirs))):
                if dirs[i][0] == "." or dirs[i] == "input":
                    del dirs[i]
            # add the files found to a list
            for fn in files:
                # ignore some files
                if fn[:3] == "pty" or fn[:3] == "tty" or fn[:3] == "ram":
                    continue
                fullname = os.path.join(root, fn)
                prepend = True
                try:
                    statinfo = os.lstat(fullname) # don't follow symbolic link
                    if stat.S_ISLNK(statinfo.st_mode):
                        statinfo = os.stat(fullname) # follow symbolic link
                        prepend = False
                except OSError, e:
                    print "Can't stat", fullname, "->", str(e)
                    continue
                # consider block devices only, take dev numbers for the keys
                if not stat.S_ISBLK(statinfo.st_mode):
                    continue
                self.add(statinfo.st_rdev, fullname, prepend)

    def add(self, key, value, prepend = False):
        lst = self._cache.get(key, [])
        if prepend:
            lst.insert(0, value)
        else:
            lst.append(value)
        self._cache[key] = lst

def getScsiDevices(path):
    """
    Returns a list of scsi device descriptors including block devices
    """
    if not os.path.isdir(path):
        return
    devs = []
    entries = os.listdir(path)
    for entry in entries:
        try:
            d = ScsiDevice(path, entry)
        except MyError, e:
            logging.warning("Init failed for "+entry+": "+str(e))
            continue
        else:
            assert d.isValid(), "Device not valid: "+entry
            # add the device in chronological order
            i = 0
            for oldDev in devs:
                if oldDev.timeStamp() < d.timeStamp():
                    break
                i += 1
            devs.insert(i, d)
    return devs

# dictionary for io filename lookup and caching
DEVICE_FILE_CACHE = DeviceFileCache()

# get initial system status
STATUS = Status()

# vim: set ts=4 sts=4 sw=4 tw=0:
