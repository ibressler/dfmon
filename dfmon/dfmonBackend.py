# -*- coding: utf-8 -*-
# dfmonBackend.py
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
But does not yet support LVM, md or multipath setups (usually not used in desktop scenarios).
"""

import sys
import os
import glob
import stat
import subprocess
import time
import math

# required system paths
OsDevPath = "/dev/"
OsSysPath = "/sys/class/scsi_device/"

# graphical sudo handlers to test for, last one is the fallback solution
plainSudoQuestion = "askforpwd"
knownSudoHandlers = [["kdesu", "-c"], ["gksudo"], ["sudo", "-p", plainSudoQuestion, "-self"], ["su", "-c"]]

# were does this come from, how to determine this value ?
blockSize = long(512)

# we support disks and cdrom/dvd drives
supportedDeviceTypes = [0, 5]

# size/capacity formatting data
magnitude = long(1024)
sizesNames = ["P", "T", "G", "M", "K", "B"]
sizesValues = []
for i in reversed(range(0,len(sizesNames))):
    sizesValues.append(pow(magnitude,i))

# time formatting data, based on seconds
timeNames = ["y", "w", "d", "h", "m", "s"]
timeValues = [31536000, 604800, 86400, 3600, 60, 1]

# output indent level used for console output
outputIndent = ""

# dictionary for io filename lookup and caching
ioFileCache = None

## implementation ##

def formatSize(size):
    """Formats the given number to human readable size information in bytes"""
    if not size or size < 0:
        return "-1"
    for v, n in zip(sizesValues, sizesNames):
        short = float(size) / float(v)
        if short >= 1.0:
            return "%.2f%s" % (short, n)
    else:
        return "%.2f%s" % (short, n)

def formatTimeDistance(t):
    if not t: return "-1"
    if t < 0: t = abs(t)
    str = ""
    for v, n in zip(timeValues, timeNames):
        if len(str) > 0:
            str += " "
        if t > v:
            factor = int(t/v)
            str += "%d%s" % (factor, n)
            t -= factor * v
    return str

def strInList(searchStr):
    return lambda line: line.find(searchStr) >= 0

def removeLineBreak(text):
    return text.strip(" \r\t\n")

def getLineFromFile(filename):
    """Reads a single line (first one) from a file with the specified name."""
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
    def __init__(self, cmdList = [], returnCode = 0, stderr = ""):
        StandardError.__init__(self)
        self.cmdList = cmdList
        self.returnCode = returnCode
        self.stderr = stderr
    def __str__(self):
        return "CmdReturnCodeError: "+str(self.returnCode)+"\n" \
                +" ".join(self.cmdList)+"\n" \
                +self.stderr

class DeviceInUseWarning(UserWarning): pass
class DeviceHasPartitionsWarning(UserWarning): pass
class RemovalSuccessInfo(Exception): pass

class SysCmd:
    __cmd = None # Popen object of the last command called
    __cmdList = None # command string list of the last command
    __cmdStatus = None # exit status of the recently invoked command
    _sudo = None
    
    def __init__(self, cmdList, sudo = False):
        """Calls a system command in a subprocess asynchronously.
        Does not block. Raises an exception if the command was not found.
        """
        self._sudo = False
        if not cmdList or len(cmdList) <= 0:
            raise MyError("No command supplied!")
        if sudo:
            newcmd = status.sudoHandler()[1:] # omit command name
            if "-c" in newcmd[-1]: # 'su -c' needs cmd as single string
                newcmd.append(" ".join(cmdList))
            else:
                newcmd.extend(cmdList)
            cmdList = newcmd
            self._sudo = True
        try:
            self.__cmd = subprocess.Popen(cmdList,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE)
        except Exception, e:
            raise MyError("Failed to run command: \n'"+
                                    " ".join(cmdList)+"': \n"+str(e))
        else:
            self.__cmdList = cmdList
            self.__cmdStatus = self.__cmd.poll()

    def cmdFinished(self):
        if not self.__cmd or self.__cmd.poll() != None:
            return True
        else:
            return False

    def cmdStatusChanged(self):
        if self.__cmdStatus != self.__cmd.poll():
            self.__cmdStatus = self.__cmd.poll()
            return True
        else: # nothing changed
            return False

    def output(self):
        """Blocks until the last command finished.
        On success, returns a list of output lines.
        Raises an exception if the return code of the last command is not 0.
        """
        if not self.__cmd: 
            return []
        stdout = []
        stderr = []
        while not self.cmdFinished():
            if self.__cmd.stderr:
                err = self.__cmd.stderr.read(len(plainSudoQuestion)).strip()
                if (self._sudo and
                    status.sudoHandler()[0] == "sudo" and
                    err == plainSudoQuestion):
                    # catch and handle sudo pwd question
                    if status.sudoPwdFct:
                        self.__cmd.stdin.write(status.sudoPwdFct()+"\n")
                    else:
                        self.__cmd.stdin.write("\n")
                else:
                    err += self.__cmd.stderr.readline()
                stderr.append(err) # preserve possible error msgs
            time.sleep(0.1) # wait some time for the command to finish
        self.cmdStatusChanged()
        returncode = self.__cmd.poll()
        if self.__cmd.stderr:
            stderr.extend(self.__cmd.stderr.readlines())
        if returncode != None and returncode != 0:
            raise CmdReturnCodeError(self.__cmdList, returncode, "\n".join(stderr))
        # no error
        if self.__cmd.stdout:
            stdout.extend(self.__cmd.stdout.readlines())
        return stdout

class Status:
    """Retrieves system status regarding Scsi, associated block devices and mountpoints."""
    __mountStatus = None
    __swapStatus = None
    __devStatus = None # simple list of scsi device names available
    __devList = None # list of devices
    __sudo = None # sudo handler for the current system
    sudoPwdFct = None # The function to call when a sudo password is required. 
                      # It has to return a string.

    def __init__(self):
        if sys.platform != "linux2":
            raise MyError("This tool supports Linux only (yet).")
        for path in OsDevPath, OsSysPath:
            if not os.path.isdir(path):
                raise MyError("Specified device path '"+path+"' does not exist !")

    def sudoHandler(self):
        if not self.__sudo or len(self.__sudo) == 0:
            self.__sudo = None
            for handler in knownSudoHandlers:
                for path in os.environ["PATH"].split(":"):
                    handlerPath = os.path.join(path, handler[0])
                    if not os.path.isfile(handlerPath):
                        continue
                    # keep the plain command name, add the full path
                    self.__sudo = handler[1:] # arguments
                    self.__sudo[:0] = [handler[0], handlerPath] # prepend command
                    if self._sudoHandlerWorks():
                        break
                if self._sudoHandlerWorks():
                    break
        if not self.__sudo or len(self.__sudo) == 0:
            raise MyError("No sudo handler found: "+str(knownSudoHandlers))
        else:
            return self.__sudo

    def _sudoHandlerWorks(self):
        if self.__sudo is None:
            return False
        try:
            text = "sudotest"
            cmd = SysCmd(["echo -n {0}".format(text)], sudo=True)
            if cmd.output()[0] != text:
                raise Exception
        except Exception, e:
            self.__sudo = None
            return False
        else:
            return True

    def update(self):
        self.devStatusChanged()
        self.mountStatusChanged()
        self.__swapStatus = SwapStatus()
        self.__devList = getScsiDevices(OsSysPath)

    def devStatusChanged(self):
        devStatus = [os.path.basename(p) for p in glob.glob(OsSysPath+os.sep+"*")]
        if not self.__devStatus or len(self.__devStatus) != len(devStatus):
            self.__devStatus = devStatus
            return True
        # compare lists, same length
        for d in self.__devStatus:
            if not d in devStatus:
                self.__devStatus = devStatus
                return True
        return False

    def mountStatusChanged(self):
        mountStatus = MountStatus()
        if not self.__mountStatus or self.__mountStatus != mountStatus:
            self.__mountStatus = mountStatus
            return True
        return False

    def getDevices(self):
        self.update()
        return self.__devList

    def swap(self): return self.__swapStatus
    def mount(self): return self.__mountStatus

class SwapStatus:
    """Summary of active swap partitions or devices"""

    __swapData = None
    __devices = None

    def __init__(self):
        """Returns the output of the 'swapon -s' command, line by line"""
        cmd = SysCmd(["/sbin/swapon","-s"])
        self.__swapData = cmd.output()
        # get a list of swap devices
        self.__devices = []
        for line in self.__swapData:
            lineList = line.replace("\t"," ").split()
            if lineList[1] != "partition":
                continue
            self.__devices.append(lineList[0])

    def isSwapDev(self, ioFile):
        if not self.__devices or len(self.__devices) < 1:
            return False
        resList = filter(strInList(ioFile), self.__devices)
        if resList and len(resList) > 0:
            return True
        else:
            return False

class MountStatus:
    """Status of all the filesystems mounted in the system"""

    __mountData = None

    def __init__(self):
        """Returns the output of the 'mount' command, line by line"""
        cmd = SysCmd(["mount"])
        self.__mountData = cmd.output()

    def __eq__(self, other):
        return "".join(self.__mountData) == "".join(other.data())

    def __ne__(self, other):
        return not self.__eq__(other)

    def data(self):
        return self.__mountData

    def getMountPoint(self, ioFile):
        if not self.__mountData or len(self.__mountData) < 1:
            return ""
        resList = filter(strInList(ioFile+" "), self.__mountData)
        mountPoint = ""
        if resList and len(resList) > 0:
            mountPoint = resList[0].split("on")[1]
            mountPoint = mountPoint.split("type")[0]
            mountPoint = removeLineBreak(mountPoint)
        else:
            global status
            if status.swap().isSwapDev(ioFile):
                mountPoint = "swap"
        return mountPoint

class Device:
    __sysfsPath = None # path to the device descriptor in /sys/

    def __init__(self, path = ""):
        path = os.path.realpath(path)
        self.setSysfs(path)

    def sysfs(self):
        return self.__sysfsPath

    def setSysfs(self, path):
        if not os.path.isdir(path):
            raise MyError("Device path does not exist: "+path)
        self.__sysfsPath = path

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
    __devName = None
    __ioFile = None
    __devNum = None
    __size = None
    __partitions = None # list of BlockDevices
    __holders = None    # list of BlockDevices
    __mountPoint = None
    __timeStamp = None

    # getter methods

    def shortName(self):
        return os.path.basename(self.ioFile())

    def fullName(self):
        return self.ioFile()

    def ioFile(self): 
        """Returns the absolute filename of the block device file (usually in /dev/)."""
        if not self.__ioFile: return ""
        return self.__ioFile

    def mountPoint(self): 
        """Returns the absolute path where this device is mounted. Empty if unmounted."""
        if not self.__mountPoint: return ""
        return self.__mountPoint

    def size(self): 
        """Returns the block devices size in bytes."""
        if not self.__size: return -1
        return self.__size

    def partitions(self): 
        """Returns the partitions as list of BlockDevices"""
        if not self.__partitions: return []
        return self.__partitions

    def holders(self): 
        """Returns the holders as list of BlockDevices"""
        if not self.__holders: return []
        return self.__holders

    def isBlock(self): return True

    # setup code

    def __init__(self, sysfsPath, blkDevName):
        Device.__init__(self, sysfsPath)
        self.setSysfs(self.sysfs() + os.sep)
        self.__devName = blkDevName
        self.__size = getSize(sysfsPath)
        if self.__size < 0:
            raise MyError("Could not determine block device size")
        self.getDeviceNumber()
        self.__ioFile = getIoFilename(self.__devNum)
        if not os.path.exists(self.__ioFile):
            raise MyError("Could not find IO device path '"
                          +self.__ioFile+"'")
        self.timeStamp()
        self.update()
        # final verification
        if not self.isValid():
            raise MyError("Determined block device information not valid")

    def update(self):
        # determine mount point
        self.__mountPoint = status.mount().getMountPoint(self.__ioFile)
        if self.__mountPoint != "swap" and not os.path.isdir(self.__mountPoint):
            self.__mountPoint = None
        # get partitions eventually
        partitions = self.getSubDev(self.sysfs(), self.__devName+"*")
        self.__partitions = []
        addSubDevices(self.__partitions, partitions, self.sysfs())
        # get holders eventually
        basePath = self.sysfs()+"holders"+os.sep
        holders = self.getSubDev(basePath, "*")
        self.__holders = []
        addSubDevices(self.__holders, holders, basePath)

    def inUse(self):
        if self.__holders and len(self.__holders) > 0:
            for h in self.__holders:
                if h.inUse():
                    return True
        if self.__partitions and len(self.__partitions) > 0:
            for p in self.__partitions:
                if p.inUse():
                    return True
        if self.__mountPoint:
            return True
        return False

    def getSubDev(self, basePath, matchStr):
        """Returns a list of sub-devices (partitions and holders/dependents)"""
        if not self.isValid():
            return []
        entries = glob.glob(basePath + matchStr)
        if not entries: 
            return []
        # return a list of the holder names relative to the input block path
        relList = [ absPath[len(basePath):] for absPath in entries ]
        return relList

    def __str__(self):
        res = ""
        for attr in [self.__devName, self.__ioFile, self.__mountPoint, 
                     formatSize(self.__size), self.__devNum, self.sysfs()]:
            res = res + str(attr) + " "

        global outputIndent
        outputIndent = outputIndent + "  "
        prefix = "\n" + outputIndent
        if self.__holders:
            res = res + prefix + "[holders:]"
            for h in self.__holders:
                res = res + prefix + str(h)
        elif self.__partitions:
            res = res + prefix + "[partitions:]"
            for p in self.__partitions:
                res = res + prefix + str(p)
        else:
            pass

        outputIndent = outputIndent[:-2]

        return res

    def isValid(self):
        return self.__devName and \
                os.path.isdir(self.sysfs()) and \
                os.path.exists(self.__ioFile) and \
                self.__devNum > 0 and \
                self.__size >= 0

    def timeStamp(self):
        """Get the time this device was added to the system."""
        if not self.__timeStamp:
            if not os.path.exists(self.ioFile()):
                self.__timeStamp = -1
            else:
                try:
                    statinfo = os.stat(self.ioFile())
                except Exception, e:
                    self.__timeStamp = -1
                else:
                    mtime = statinfo[stat.ST_MTIME]
                    atime = statinfo[stat.ST_ATIME]
                    ctime = statinfo[stat.ST_CTIME]
                    self.__timeStamp = mtime
                    # get the oldest timestamp
                    if atime < self.__timeStamp:
                        self.__timeStamp = atime
                    if ctime < self.__timeStamp:
                        self.__timeStamp = ctime
        return self.__timeStamp

    def getDeviceNumber(self):
        if not self.__devNum:
            fn = os.path.join(self.sysfs(),"dev")
            if not os.path.isfile(fn):
                return -1
            (major, minor) = getLineFromFile(fn).split(":")
            if not major or not minor or major < 0 or minor < 0:
                return -1
            self.__devNum = os.makedev(int(major), int(minor))
        return self.__devNum

    def mount(self, password = None):
        """Mount block device"""
        # no partitions
        if len(self.__partitions) == 0:
            if not os.path.exists(self.ioFile()): return
            if self.inUse():
                raise DeviceInUseWarning()
            else:
                try:
                    if password is not None:
                        cmd = SysCmd(["truecrypt", "-t", "--non-interactive",
                                      "-p", password, "--mount", self.ioFile()],
                                     sudo = True)
                    else:
                        cmd = SysCmd(["truecrypt", "--mount",
                                      self.ioFile()], sudo = True)
                    cmd.output()
                except MyError, e:
                    raise MyError("Failed to mount "+self.ioFile()+": "+str(e))
        elif len(self.__partitions) == 1:
            self.__partitions[0].mount()
        else:
            raise DeviceHasPartitionsWarning()
        self.update()

    def umount(self):
        """Unmount block device"""
        for part in self.__partitions:
            part.umount()
        for holder in self.__holders:
            holder.umount()
        if not os.path.isdir(self.mountPoint()):
            return
        # function tests for truecrypt device files
        isTruecrypt = strInList("truecrypt")
        try:
            cmd = None
            if isTruecrypt(self.__ioFile):
                # --non-interactive
                cmd = SysCmd(["truecrypt", "-t", "--non-interactive", "-d", self.mountPoint()], True)
            else:
                cmd = SysCmd(["umount", self.mountPoint()], True)
            stdout = "".join(cmd.output())
            if len(stdout) > 0 and stdout != "passprompt":
                raise MyError(stdout)
        except MyError, e:
            raise MyError("Failed to umount "+self.ioFile()+": \n"+str(e))
        self.update()

    def flush(self):
        """Flushes the device buffers."""
#        print "flush", self.ioFile()
        for part in self.__partitions:
            part.flush()
        for holder in self.__holders:
            holder.flush()
        if self.inUse() or not os.path.exists(self.ioFile()):
            return
        try:
            cmd = SysCmd(["/sbin/blockdev", "--flushbufs", self.ioFile()], True)
            cmd.output()
        except CmdReturnCodeError, e:
            # what to do on fail, ignore ?
            raise MyError(str(e))

def getSize(sysfsPath):
    """Returns the overall numerical size of a block device.
    arg: absolute path to the block device descriptor"""
    if not os.path.isdir(sysfsPath):
        return -1
    fn = os.path.join(sysfsPath, "size")
    text = getLineFromFile(fn)
    if text.isdigit():
        return long(text)*blockSize
    else:
        return -1

def addSubDevices(outList, devNameList, basePath):
    """Creates block devices from a device name list and adds them to outList \
    in:     directory path where the device names from the list exist
    in:     list of device names
    in/out: list of valid block devices"""
    if outList == None or not devNameList:
        return
    # add all partitions as block devices (recursive)
    for devName in devNameList:
        queryPath = os.path.join(basePath,devName)
        if not os.path.isdir(queryPath):
            continue
        dev = BlockDevice(queryPath, devName)
        if not dev.isValid():
            raise MyError("Not Valid")
        outList.append(dev)

### end BlockDevice related stuff

class ScsiDevice(Device):
    __scsiAdr = None # list with <host> <channel> <id> <lun>
    __dev = None     # associated Block device object
    __driverName = None
    __vendor = None
    __model = None

    # getter methods

    def shortName(self):
        return self.scsiStr()

    def fullName(self):
        return self.scsiStr()+" "+self.model()

    def blk(self): 
        """Returns the associated BlockDevice."""
        return self.__dev

    def scsiStr(self): 
        """Returns the SCSI address of this device as string."""
        if not self.__scsiAdr: return ""
        return "["+reduce(lambda a, b: a+":"+b, self.__scsiAdr)+"]"

    def isScsi(self): return True

    # forwarder

    def inUse(self): 
        """Tells if this device is in use somehow (has mounted partitions)."""
        return self.__dev.inUse()

    def mount(self): return self.__dev.mount()
    def umount(self): return self.__dev.umount()
    def flush(self): return self.__dev.flush()

    # setup code

    def __init__(self, path, scsiStr):
        Device.__init__(self, os.path.join(path, scsiStr, "device"))
        self.__scsiAdr = scsiStr.split(":")
        if not self.isSupported():
            # throw exception here
            raise MyError("Device type not supported")
        path, name = getBlkDevPath(self.sysfs())
        if not name or not path:
            # throw exception
            raise MyError("Could not determine block device path in /sys/")
        self.__dev = BlockDevice(path, name)
        self.driver()
        self.vendor()
        self.model()
        self.timeStamp()
        # final verification
        if not self.isValid():
            raise MyError("Determined Scsi device information not valid")

    def model(self):
        if self.__model and len(self.__model) > 0:
            return self.__model
        self.__model = ""
        fn = os.path.join(self.sysfs(),"model")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                self.__model = txt
        return self.__model

    def vendor(self):
        if self.__vendor and len(self.__vendor) > 0:
            return self.__vendor
        self.__vendor = ""
        fn = os.path.join(self.sysfs(),"vendor")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                self.__vendor = txt
        return self.__vendor

    def driver(self):
        if self.__driverName and len(self.__driverName) > 0:
            return self.__driverName
        sysfsPath = self.__dev.sysfs()
        if not os.path.isdir(sysfsPath):
            return ""
        path = os.path.realpath(os.path.join(sysfsPath,"device"))
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        path = os.path.realpath(os.path.join(path,"driver"))
        (path,tail) = os.path.split(path)
        self.__driverName = tail
        return self.__driverName

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
        type = int(txt)
        for t in supportedDeviceTypes:
            if type == t:
                return True
        else:
            return False

    def isValid(self):
        return (len(self.__scsiAdr) == 4 and
                self.sysfs() and os.path.isdir(self.sysfs()) and
                self.__dev.isValid())
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
                self.__dev.flush()
                try:
                    cmd = SysCmd(["sh -c 'echo 1 > "+delPath+"'"], True)
                except CmdReturnCodeError, e:
                    raise MyError(str(e))
                else:
                    if not self.isValid():
                        raise RemovalSuccessInfo()

    def __str__(self):
        """Outputs full detailed information about this devices"""
        if not self.isValid():
            return "not valid!"
        output = str(self.__scsiAdr) + \
                ", in use: " + str(self.__dev.inUse()) + \
                ", driver: " + str(self.__driverName) + \
                ", vendor: " + str(self.__vendor) + \
                ", model: " + str(self.__model) + \
                "\n" + str(self.__dev)
        return output

def getBlkDevPath(devPath):
    """Returns the scsi block device path.
    in: path to the scsi device
    out: path to the associated block device AND the block device name"""
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

# how to improve this ? is there a direct way to get the device file ?
# speedup by caching ?
def getIoFilename(devNum):
    """Search the block device filename in /dev/ based on the major/minor number"""
    if not devNum or devNum < 0:
        return ""
    foundName = ""
    global ioFileCache
    if not ioFileCache or len(ioFileCache) == 0 or not ioFileCache.has_key(devNum):
        rebuildIoFileCache()
    # retrieve the io file if available
    foundName = ioFileCache.get(devNum, "")
    return foundName

def rebuildIoFileCache():
    global ioFileCache
    if not ioFileCache:
        ioFileCache = dict()
    ioFileCache.clear()
    for root, dirs, files in os.walk(OsDevPath):
        # ignore directories with leading dot
        for i in reversed(range(0,len(dirs))):
            if dirs[i][0] == "." or dirs[i] == "input":
                del dirs[i]
        # add the files found to a list
        for fn in files:
            # ignore some files
            if fn[0:3] == "pty" or fn[0:3] == "tty" or fn[0:3] == "ram":
                continue
            fullName = os.path.join(root,fn)
            try:
                statinfo = os.lstat(fullName) # no symbolic links !
            except OSError, e:
                print "Can't stat",fullName,"->",str(e)
                continue
            else:
                # consider block devices only, take device numbers for the keys
                if stat.S_ISBLK(statinfo.st_mode):
                    ioFileCache[statinfo.st_rdev] = fullName

def getScsiDevices(path):
    """Returns a list of scsi device descriptors including block devices"""
    if not os.path.isdir(path):
        return
    devs = []
    entries = os.listdir(path)
    for entry in entries:
        try:
            d = ScsiDevice(path, entry)
        except MyError, e:
            raise MyError("Init failed for "+entry+": "+str(e))
        else:
            if not d.isValid():
                raise MyError("Device not valid: "+entry)
            else:
                # add the device in chronological order
                i = 0
                for oldDev in devs:
                    if oldDev.timeStamp() < d.timeStamp():
                        break
                    i += 1
                devs.insert(i, d)
    return devs

# get initial system status
status = Status()

# vim: set ts=4 sw=4 tw=0:
