"""hotplug mgr backend intelligence

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

# required system paths
OsDevPath = "/dev/"
OsSysPath = "/sys/class/scsi_device/"

# graphical sudo handlers to test for, last one is the fallback solution
knownSudoHandlers = ["kdesudo", "gksudo", "sudo"]

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

# output indent level used for console output
outputIndent = ""


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

class MyError(UserWarning):
    def __init__(s, msg):
        UserWarning.__init__(s)
        s.msg = msg
    def __str__(s):
        return str(s.msg)
    def __repr__(s):
        return repr(s.msg)

class CmdReturnCodeError(UserWarning):
    def __init__(s, returnCode, stderr):
        UserWarning.__init__(s)
        s.returnCode = returnCode
        s.stderr = stderr
    def __str__(s):
        return "CmdReturnCodeError: "+str(s.returnCode)

class DeviceInUseWarning(UserWarning): pass
class DeviceHasPartitions(UserWarning): pass
class MissingPrivileges(UserWarning): pass

class Status:
    """Retrieves system status regarding Scsi, associated block devices and mountpoints."""
    __mountStatus = None
    __swapStatus = None
    __devList = None # list of devices
    __sudo = None
    __lastCmd = None # Popen object of the last command called
    __lastCmdList = None # command string list of the last command

    def __init__(s):
        if sys.platform != "linux2":
            raise MyError("This tool supports Linux only (yet).")
        for path in OsDevPath, OsSysPath:
            if not os.path.isdir(path):
                raise MyError("Specified device path '"+path+"' does not exist !")
        s.setSudoHandler()

    def setSudoHandler(s):
        for handler in knownSudoHandlers:
            for path in os.environ["PATH"].split(":"):
                handlerPath = os.path.join(path, handler)
                if os.path.isfile(handlerPath):
                    s.__sudo = handlerPath
                    return

    def update(s):
        s.__mountStatus = MountStatus()
        s.__swapStatus = SwapStatus()
        s.__devList = getScsiDevices(OsSysPath)

    def getDevices(s):
        s.update()
        return s.__devList

    def lastCmdName(s):
        if not s.__lastCmdList or not s.__lastCmdList[0]:
            return ""
        return str(s.__lastCmdList[0])

    def swap(s): return s.__swapStatus
    def mount(s): return s.__mountStatus

    def callSysCommand(s, cmdList, sudoFlag = False):
        if not cmdList or len(cmdList) <= 0:
            return
        if sudoFlag:
#            cmdList = [s.__sudo, " ".join(cmdList)]
            cmdList.insert(0, "--")
            cmdList.insert(0, s.__sudo)
        try:
            print "callSysCommand:", str(cmdList)
            s.__lastCmd = subprocess.Popen(cmdList, bufsize=-1, 
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except Exception, e:
            raise MyError("Failed to run command: \n'"+
                                    " ".join(cmdList)+"': \n"+str(e))
        finally:
            s.__lastCmdList = cmdList

    def lastCmdOutput(s):
        "On success, returns a list of output lines."
        if not s.__lastCmd: 
            return []
        #while s.__lastCmd.returncode == None:
#        time.sleep(0.1) # wait some time for the usual command to finish
    #    if retCode == None:
    #        mountCmd.kill() # probably blocked by hardware, avoid stalling, py v2.6
        returncode = s.__lastCmd.poll()
        while returncode == None:
            returncode = s.__lastCmd.poll()
            time.sleep(0.1) # wait some time for the command to finish
        if returncode != None and returncode != 0:
            stderr = ""
            if s.__lastCmd.stderr != None:
                stderr = "\n".join(s.__lastCmd.stderr.readlines())
            raise CmdReturnCodeError(returncode, stderr)
        # no error
        stdout = []
        if s.__lastCmd.stdout != None:
                stdout = s.__lastCmd.stdout.readlines()
        return stdout

class SwapStatus:
    """Summary of active swap partitions or devices"""

    __swapData = None
    __devices = None

    def __init__(s):
        """Returns the output of the 'swapon -s' command, line by line"""
        status.callSysCommand(["swapon","-s"])
        s.__swapData = status.lastCmdOutput()
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
        status.callSysCommand(["mount"])
        s.__mountData = status.lastCmdOutput()

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

    def __init__(s, path):
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
            raise MyError("Could not find IO device path")
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

    def getSysfsPath(s):
        if not s.isValid():
            return ""
        else:
            return s.sysfs()

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

    def mount(s):
        """Mount block device"""
        # no partitions
        if len(s.__partitions) == 0:
            if not os.path.exists(s.ioFile()): return
            if s.inUse():
                raise DeviceInUseWarning()
            else:
                try:
                    status.callSysCommand(["truecrypt", "--mount", s.ioFile()])
                except MyError, e:
                    raise MyError("Failed to mount "+s.ioFile()+": "+str(e))
        elif len(s.__partitions) == 1:
            s.__partitions[0].mount()
        else:
            raise DeviceHasPartitions()
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
            if isTruecrypt(s.__ioFile):
                status.callSysCommand(["truecrypt", "-t", "-d", s.mountPoint()])
            else:
                status.callSysCommand(["umount", s.mountPoint()])
            try: # check for errors
                status.lastCmdOutput()
            except CmdReturnCodeError, e:
                if status.lastCmdName() == "umount" and e.returnCode == 2: # privileges error
                    raise MyError("You do not have the required privileges.")
                else:
                    raise MyError(e.stderr)
        except MyError, e:
            raise MyError("Failed to umount "+s.ioFile()+": \n"+str(e))
        s.update()

    def flush(s):
        """Flushes the device buffers."""
        print "flush", s.ioFile()
        for part in s.__partitions:
            part.flush()
        for holder in s.__holders:
            holder.flush()
        if s.inUse() or not os.path.exists(s.ioFile()):
            return
        try:
            status.callSysCommand(["blockdev", "--flushbufs", s.ioFile()], True)
            status.lastCmdOutput()
        except CmdReturnCodeError, e:
            raise MyError("CmdReturnCodeError: "+str(e.returnCode)+"\n"+e.stderr)

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
        try:
            dev = BlockDevice(queryPath, devName)
            if not dev.isValid():
                raise MyError("Not Valid")
        except MyError, e:
            print "Could not figure out block device ",devName,"->",e
        else:
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
        sysfsPath = s.__dev.getSysfsPath()
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
        return len(s.__scsiAdr) == 4 and \
                s.sysfs() and os.path.isdir(s.sysfs()) and \
                s.__dev.isValid()
        # test for every blk device being valid
        
    def remove(s):
        if s.inUse():
            s.umount()
        if s.inUse(): # still in use
            raise MyError("Could not umount this device!")
        else:
            delPath = os.path.join(s.sysfs(), "delete")
            if not os.path.isfile(delPath):
                raise MyError("Could not find '"+delPath+"'")
            else:
                s.__dev.flush()
                try:
                    status.callSysCommand(["su", "-c", "echo 1 > "+delPath], True)
                    status.lastCmdOutput()
                except CmdReturnCodeError, e:
                    raise MyError("CmdReturnCodeError: "+str(e.returnCode)+"\n"+e.stderr)

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
        return []
    devPath = os.path.join(devPath, "block:");
    entries = glob.glob(devPath+"*")
    if not entries:
        return []
    fullPath = entries[0]
    devName = fullPath[len(devPath):]
    return (fullPath, devName)

# how to improve this ? is there a direct way to get the device file ?
# speedup by caching ?
def getIoFilename(devNum):
    """Search the block device filename in /dev/ based on the major/minor number"""
    if not devNum or devNum < 0:
        return ""
    # get all device files first
    for root, dirs, files in os.walk(OsDevPath):
        # ignore directories with leading dot
        for i in reversed(range(0,len(dirs))):
            if dirs[i][0] == ".":
                del dirs[i]
        # add the files found to a list
        for fn in files:
            # ignore some files
            if fn[0:3] == "pty" or fn[0:3] == "tty":
                continue
            fullName = os.path.join(root,fn)
            try:
                statinfo = os.lstat(fullName) # no symbolic links !
            except OSError, e:
                print "Can't stat",fullName,"->",str(e)
                continue
            else:
                # compare device numbers on block devices
                if stat.S_ISBLK(statinfo.st_mode) and \
                   devNum == statinfo.st_rdev:
                    return fullName
    return ""

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
                devs.append(d)
    return devs

# get initial system status
status = Status()
