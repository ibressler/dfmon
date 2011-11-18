# -*- coding: utf-8 -*-
# dfmonBackend.py
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
#
# Authors:
#     Ingo Bressler (April 2010)

"""dfmon backend intelligence

Device removal procedure follows recommendations at:
http://www.redhat.com/docs/en-US/Red_Hat_Enterprise_Linux/html/Online_Storage_Reconfiguration_Guide/removing_devices.html
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
knownSudoHandlers = [["kdesu", "-c"], ["gksudo"], ["sudo", "-p", plainSudoQuestion, "-S"], ["su", "-c"]]

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
    def __init__(s, msg = ""):
        StandardError.__init__(s)
        s.msg = msg
    def __str__(s):
        return str(s.msg)
    def __repr__(s):
        return repr(s.msg)

class CmdReturnCodeError(StandardError):
    def __init__(s, cmdList = [], returnCode = 0, stderr = ""):
        StandardError.__init__(s)
        s.cmdList = cmdList
        s.returnCode = returnCode
        s.stderr = stderr
    def __str__(s):
        return "CmdReturnCodeError: "+str(s.returnCode)+"\n" \
                +" ".join(s.cmdList)+"\n" \
                +s.stderr

class DeviceInUseWarning(UserWarning): pass
class DeviceHasPartitionsWarning(UserWarning): pass
class RemovalSuccessInfo(Exception): pass

class SysCmd:
    __cmd = None # Popen object of the last command called
    __cmdList = None # command string list of the last command
    __cmdStatus = None # exit status of the recently invoked command
    
    def __init__(s, cmdList, sudoFlag = False):
        """Calls a system command in a subprocess asynchronously.
        Does not block. Raises an exception if the command was not found.
        """
        if not cmdList or len(cmdList) <= 0:
            raise MyError("No command supplied!")
        if sudoFlag:
            newcmd = status.sudoHandler()[1:] # omit command name
            if "-c" in newcmd[-1]: # 'su -c' needs cmd as single string
                newcmd.append(" ".join(cmdList))
            else:
                newcmd.extend(cmdList)
            cmdList = newcmd
        try:
            s.__cmd = subprocess.Popen(cmdList,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE)
        except Exception, e:
            raise MyError("Failed to run command: \n'"+
                                    " ".join(cmdList)+"': \n"+str(e))
        else:
            s.__cmdList = cmdList
            s.__cmdStatus = s.__cmd.poll()

    def cmdFinished(s):
        if not s.__cmd or s.__cmd.poll() != None:
            return True
        else:
            return False

    def cmdStatusChanged(s):
        if s.__cmdStatus != s.__cmd.poll():
            s.__cmdStatus = s.__cmd.poll()
            return True
        else: # nothing changed
            return False

    def output(s):
        """Blocks until the last command finished.
        On success, returns a list of output lines.
        Raises an exception if the return code of the last command is not 0.
        """
        if not s.__cmd: 
            return []
        stdout = []
        stderr = []
        while not s.cmdFinished():
            # catch and handle sudo pwd question
            if s.__cmd.stderr and status.sudoHandler()[0] == "sudo":
                err = s.__cmd.stderr.read(len(plainSudoQuestion)).strip()
                if err == plainSudoQuestion:
                    if status.sudoPwdFct:
                        s.__cmd.stdin.write(status.sudoPwdFct()+"\n")
                    else:
                        s.__cmd.stdin.write("\n")
                else:
                    err += s.__cmd.stderr.readline()
                stderr.append(err) # preserve possible error msgs
            time.sleep(0.1) # wait some time for the command to finish
        s.cmdStatusChanged()
        returncode = s.__cmd.poll()
        if s.__cmd.stderr:
            stderr.extend(s.__cmd.stderr.readlines())
        if returncode != None and returncode != 0:
            raise CmdReturnCodeError(s.__cmdList, returncode, "\n".join(stderr))
        # no error
        if s.__cmd.stdout:
            stdout.extend(s.__cmd.stdout.readlines())
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

    def __init__(s):
        if sys.platform != "linux2":
            raise MyError("This tool supports Linux only (yet).")
        for path in OsDevPath, OsSysPath:
            if not os.path.isdir(path):
                raise MyError("Specified device path '"+path+"' does not exist !")

    def sudoHandler(s):
        if not s.__sudo or len(s.__sudo) == 0:
            s.__sudo = None
            for handler in knownSudoHandlers:
                for path in os.environ["PATH"].split(":"):
                    handlerPath = os.path.join(path, handler[0])
                    if not os.path.isfile(handlerPath):
                        continue
                    # keep the plain command name, add the full path
                    s.__sudo = handler[1:] # arguments
                    s.__sudo[:0] = [handler[0], handlerPath] # prepend command
                    if s._sudoHandlerWorks():
                        break
                if s._sudoHandlerWorks():
                    break
        if not s.__sudo or len(s.__sudo) == 0:
            raise MyError("No sudo handler found: "+str(knownSudoHandlers))
        else:
            return s.__sudo

    def _sudoHandlerWorks(s):
        if s.__sudo is None:
            return False
        try:
            text = "sudotest"
            cmd = SysCmd(["echo -n {0}".format(text)], sudoFlag=True)
            if cmd.output()[0] != text:
                raise Exception
        except Exception, e:
            s.__sudo = None
            return False
        else:
            return True

    def update(s):
        s.devStatusChanged()
        s.mountStatusChanged()
        s.__swapStatus = SwapStatus()
        s.__devList = getScsiDevices(OsSysPath)

    def devStatusChanged(s):
        devStatus = [os.path.basename(p) for p in glob.glob(OsSysPath+os.sep+"*")]
        if not s.__devStatus or len(s.__devStatus) != len(devStatus):
            s.__devStatus = devStatus
            return True
        # compare lists, same length
        for d in s.__devStatus:
            if not d in devStatus:
                s.__devStatus = devStatus
                return True
        return False

    def mountStatusChanged(s):
        mountStatus = MountStatus()
        if not s.__mountStatus or s.__mountStatus != mountStatus:
            s.__mountStatus = mountStatus
            return True
        return False

    def getDevices(s):
        s.update()
        return s.__devList

    def swap(s): return s.__swapStatus
    def mount(s): return s.__mountStatus

class SwapStatus:
    """Summary of active swap partitions or devices"""

    __swapData = None
    __devices = None

    def __init__(s):
        """Returns the output of the 'swapon -s' command, line by line"""
        cmd = SysCmd(["/sbin/swapon","-s"])
        s.__swapData = cmd.output()
        # get a list of swap devices
        s.__devices = []
        for line in s.__swapData:
            lineList = line.replace("\t"," ").split()
            if lineList[1] != "partition":
                continue
            s.__devices.append(lineList[0])

    def isSwapDev(s, ioFile):
        if not s.__devices or len(s.__devices) < 1:
            return False
        resList = filter(strInList(ioFile), s.__devices)
        if resList and len(resList) > 0:
            return True
        else:
            return False

class MountStatus:
    """Status of all the filesystems mounted in the system"""

    __mountData = None

    def __init__(s):
        """Returns the output of the 'mount' command, line by line"""
        cmd = SysCmd(["mount"])
        s.__mountData = cmd.output()

    def __eq__(s, other):
        return "".join(s.__mountData) == "".join(other.data())

    def __ne__(s, other):
        return not s.__eq__(other)

    def data(s):
        return s.__mountData

    def getMountPoint(s, ioFile):
        if not s.__mountData or len(s.__mountData) < 1:
            return ""
        resList = filter(strInList(ioFile+" "), s.__mountData)
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

    def __init__(s, path = ""):
        path = os.path.realpath(path)
        s.setSysfs(path)

    def sysfs(s):
        return s.__sysfsPath

    def setSysfs(s, path):
        if not os.path.isdir(path):
            raise MyError("Device path does not exist: "+path)
        s.__sysfsPath = path

    def isBlock(s):
        """Returns True if the Device is a BlockDevice."""
        return False

    def isScsi(s):
        """Returns True if the Device is a ScsiDevice."""
        return False

    def shortName(s):
        """Returns the short device name for GUI display."""
        return ""

    def fullName(s):
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

    def shortName(s):
        return os.path.basename(s.ioFile())

    def fullName(s):
        return s.ioFile()

    def ioFile(s): 
        """Returns the absolute filename of the block device file (usually in /dev/)."""
        if not s.__ioFile: return ""
        return s.__ioFile

    def mountPoint(s): 
        """Returns the absolute path where this device is mounted. Empty if unmounted."""
        if not s.__mountPoint: return ""
        return s.__mountPoint

    def size(s): 
        """Returns the block devices size in bytes."""
        if not s.__size: return -1
        return s.__size

    def partitions(s): 
        """Returns the partitions as list of BlockDevices"""
        if not s.__partitions: return []
        return s.__partitions

    def holders(s): 
        """Returns the holders as list of BlockDevices"""
        if not s.__holders: return []
        return s.__holders

    def isBlock(s): return True

    # setup code

    def __init__(s, sysfsPath, blkDevName):
        Device.__init__(s, sysfsPath)
        s.setSysfs(s.sysfs() + os.sep)
        s.__devName = blkDevName
        s.__size = getSize(sysfsPath)
        if s.__size < 0:
            raise MyError("Could not determine block device size")
        s.getDeviceNumber()
        s.__ioFile = getIoFilename(s.__devNum)
        if not os.path.exists(s.__ioFile):
            raise MyError("Could not find IO device path '"
                          +s.__ioFile+"'")
        s.timeStamp()
        s.update()
        # final verification
        if not s.isValid():
            raise MyError("Determined block device information not valid")

    def update(s):
        # determine mount point
        s.__mountPoint = status.mount().getMountPoint(s.__ioFile)
        if s.__mountPoint != "swap" and not os.path.isdir(s.__mountPoint):
            s.__mountPoint = None
        # get partitions eventually
        partitions = s.getSubDev(s.sysfs(), s.__devName+"*")
        s.__partitions = []
        addSubDevices(s.__partitions, partitions, s.sysfs())
        # get holders eventually
        basePath = s.sysfs()+"holders"+os.sep
        holders = s.getSubDev(basePath, "*")
        s.__holders = []
        addSubDevices(s.__holders, holders, basePath)

    def inUse(s):
        if s.__holders and len(s.__holders) > 0:
            for h in s.__holders:
                if h.inUse():
                    return True
        if s.__partitions and len(s.__partitions) > 0:
            for p in s.__partitions:
                if p.inUse():
                    return True
        if s.__mountPoint:
            return True
        return False

    def getSubDev(s, basePath, matchStr):
        """Returns a list of sub-devices (partitions and holders/dependents)"""
        if not s.isValid():
            return []
        entries = glob.glob(basePath + matchStr)
        if not entries: 
            return []
        # return a list of the holder names relative to the input block path
        relList = [ absPath[len(basePath):] for absPath in entries ]
        return relList

    def __str__(s):
        res = ""
        for attr in [s.__devName, s.__ioFile, s.__mountPoint, 
                     formatSize(s.__size), s.__devNum, s.sysfs()]:
            res = res + str(attr) + " "

        global outputIndent
        outputIndent = outputIndent + "  "
        prefix = "\n" + outputIndent
        if s.__holders:
            res = res + prefix + "[holders:]"
            for h in s.__holders:
                res = res + prefix + str(h)
        elif s.__partitions:
            res = res + prefix + "[partitions:]"
            for p in s.__partitions:
                res = res + prefix + str(p)
        else:
            pass

        outputIndent = outputIndent[:-2]

        return res

    def isValid(s):
        return s.__devName and \
                os.path.isdir(s.sysfs()) and \
                os.path.exists(s.__ioFile) and \
                s.__devNum > 0 and \
                s.__size >= 0

    def timeStamp(s):
        """Get the time this device was added to the system."""
        if not s.__timeStamp:
            if not os.path.exists(s.ioFile()):
                s.__timeStamp = -1
            else:
                try:
                    statinfo = os.stat(s.ioFile())
                except Exception, e:
                    s.__timeStamp = -1
                else:
                    mtime = statinfo[stat.ST_MTIME]
                    atime = statinfo[stat.ST_ATIME]
                    ctime = statinfo[stat.ST_CTIME]
                    s.__timeStamp = mtime
                    # get the oldest timestamp
                    if atime < s.__timeStamp:
                        s.__timeStamp = atime
                    if ctime < s.__timeStamp:
                        s.__timeStamp = ctime
        return s.__timeStamp

    def getDeviceNumber(s):
        if not s.__devNum:
            fn = os.path.join(s.sysfs(),"dev")
            if not os.path.isfile(fn):
                return -1
            (major, minor) = getLineFromFile(fn).split(":")
            if not major or not minor or major < 0 or minor < 0:
                return -1
            s.__devNum = os.makedev(int(major), int(minor))
        return s.__devNum

    def mount(s, password = None):
        """Mount block device"""
        # no partitions
        if len(s.__partitions) == 0:
            if not os.path.exists(s.ioFile()): return
            if s.inUse():
                raise DeviceInUseWarning()
            else:
                try:
                    if password is not None:
                        cmd = SysCmd(["truecrypt", "-t", "--non-interactive",
                                      "-p", password, "--mount", s.ioFile()],
                                     sudoFlag = True)
                    else:
                        cmd = SysCmd(["truecrypt", "--mount",
                                      s.ioFile()], sudoFlag = True)
                    cmd.output()
                except MyError, e:
                    raise MyError("Failed to mount "+s.ioFile()+": "+str(e))
        elif len(s.__partitions) == 1:
            s.__partitions[0].mount()
        else:
            raise DeviceHasPartitionsWarning()
        s.update()

    def umount(s):
        """Unmount block device"""
        for part in s.__partitions:
            part.umount()
        for holder in s.__holders:
            holder.umount()
        if not os.path.isdir(s.mountPoint()):
            return
        # function tests for truecrypt device files
        isTruecrypt = strInList("truecrypt")
        try:
            cmd = None
            if isTruecrypt(s.__ioFile):
                # --non-interactive
                cmd = SysCmd(["truecrypt", "-t", "--non-interactive", "-d", s.mountPoint()], True)
            else:
                cmd = SysCmd(["umount", s.mountPoint()], True)
            stdout = "".join(cmd.output())
            if len(stdout) > 0 and stdout != "passprompt":
                raise MyError(stdout)
        except MyError, e:
            raise MyError("Failed to umount "+s.ioFile()+": \n"+str(e))
        s.update()

    def flush(s):
        """Flushes the device buffers."""
#        print "flush", s.ioFile()
        for part in s.__partitions:
            part.flush()
        for holder in s.__holders:
            holder.flush()
        if s.inUse() or not os.path.exists(s.ioFile()):
            return
        try:
            cmd = SysCmd(["/sbin/blockdev", "--flushbufs", s.ioFile()], True)
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

    def shortName(s):
        return s.scsiStr()

    def fullName(s):
        return s.scsiStr()+" "+s.model()

    def blk(s): 
        """Returns the associated BlockDevice."""
        return s.__dev

    def scsiStr(s): 
        """Returns the SCSI address of this device as string."""
        if not s.__scsiAdr: return ""
        return "["+reduce(lambda a, b: a+":"+b, s.__scsiAdr)+"]"

    def isScsi(s): return True

    # forwarder

    def inUse(s): 
        """Tells if this device is in use somehow (has mounted partitions)."""
        return s.__dev.inUse()

    def mount(s): return s.__dev.mount()
    def umount(s): return s.__dev.umount()
    def flush(s): return s.__dev.flush()

    # setup code

    def __init__(s, path, scsiStr):
        Device.__init__(s, os.path.join(path, scsiStr, "device"))
        s.__scsiAdr = scsiStr.split(":")
        if not s.isSupported():
            # throw exception here
            raise MyError("Device type not supported")
        path, name = getBlkDevPath(s.sysfs())
        if not name or not path:
            # throw exception
            raise MyError("Could not determine block device path in /sys/")
        s.__dev = BlockDevice(path, name)
        s.driver()
        s.vendor()
        s.model()
        s.timeStamp()
        # final verification
        if not s.isValid():
            raise MyError("Determined Scsi device information not valid")

    def model(s):
        if s.__model and len(s.__model) > 0:
            return s.__model
        s.__model = ""
        fn = os.path.join(s.sysfs(),"model")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                s.__model = txt
        return s.__model

    def vendor(s):
        if s.__vendor and len(s.__vendor) > 0:
            return s.__vendor
        s.__vendor = ""
        fn = os.path.join(s.sysfs(),"vendor")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                s.__vendor = txt
        return s.__vendor

    def driver(s):
        if s.__driverName and len(s.__driverName) > 0:
            return s.__driverName
        sysfsPath = s.__dev.sysfs()
        if not os.path.isdir(sysfsPath):
            return ""
        path = os.path.realpath(os.path.join(sysfsPath,"device"))
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        path = os.path.realpath(os.path.join(path,"driver"))
        (path,tail) = os.path.split(path)
        s.__driverName = tail
        return s.__driverName

    def timeStamp(s):
        """Get the time this device was added to the system."""
        return s.blk().timeStamp()

    def isSupported(s):
        fn = os.path.join(s.sysfs(),"type")
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

    def isValid(s):
        return (len(s.__scsiAdr) == 4 and
                s.sysfs() and os.path.isdir(s.sysfs()) and
                s.__dev.isValid())
        # test for every blk device being valid

    def remove(s):
        if s.inUse():
            s.umount()
        ts = time.time()
        # wait a sec
        while s.inUse() and time.time() < ts+1.5:
            time.sleep(0.1)
        # still in use
        if s.inUse():
            raise MyError("Could not umount this device!")
        else:
            # not in use anymore, remove the device
            delPath = os.path.join(s.sysfs(), "delete")
            if not os.path.isfile(delPath):
                raise MyError("Could not find '"+delPath+"'")
            else:
                s.__dev.flush()
                try:
                    cmd = SysCmd(["sh -c 'echo 1 > "+delPath+"'"], True)
                except CmdReturnCodeError, e:
                    raise MyError(str(e))
                else:
                    if not s.isValid():
                        raise RemovalSuccessInfo()

    def __str__(s):
        """Outputs full detailed information about this devices"""
        if not s.isValid():
            return "not valid!"
        output = str(s.__scsiAdr) + \
                ", in use: " + str(s.__dev.inUse()) + \
                ", driver: " + str(s.__driverName) + \
                ", vendor: " + str(s.__vendor) + \
                ", model: " + str(s.__model) + \
                "\n" + str(s.__dev)
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
