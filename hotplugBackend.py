import sys
import os
import glob
import stat
import subprocess
import time

# were does this come from, how to determine this value ?
blockSize = long(512)

# we support disks and cdrom/dvd drives
supportedDeviceTypes = [0, 5]

magnitude = long(1024)
sizesNames = ["P", "T", "G", "M", "K", "B"]
sizesValues = []
for i in reversed(range(0,len(sizesNames))):
    sizesValues.append(pow(magnitude,i))

# output indent level used for console output
outputIndent = ""

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

def makeRel(basePath):
    return lambda absPath: absPath[len(basePath):]

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


def callSysCommand(cmdList):
    if not cmdList or len(cmdList) <= 0:
        return ""
    cmd = subprocess.Popen(cmdList, bufsize=-1, \
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    time.sleep(0.1) # wait some time for the usual command to finish
    retCode = cmd.poll()
#    if retCode == None:
#        mountCmd.kill() # probably blocked by hardware, avoid stalling
    (stdout, stderr) = cmd.communicate()
    if retCode != 0 and retCode != None:
        raise MyError("Failed to run command '"+
                      cmdList[0]+"', returned: "+ 
                      str(retCode)+"\n"+stderr)
    return stdout

class MyError(UserWarning):
    def __init__(s, msg):
        s.msg = msg
    def __str__(s):
        return str(s.msg)
    def __repr__(s):
        return repr(s.msg)

class DeviceInUseWarning(UserWarning): pass


class Status:
    _osDevPath = "/dev/"
    _osSysPath = "/sys/class/scsi_device/"
    _mountStatus = None
    _swapStatus = None
    _devList = None # list of devices

    def __init__(s):
        if sys.platform != "linux2":
            raise MyError("This tool is for Linux only !")
        for path in s._osDevPath, s._osSysPath:
            if not os.path.isdir(path):
                raise MyError("Specified device path '"+path+"' does not exist !")

    def update(s):
        s._mountStatus = MountStatus()
        s._swapStatus = SwapStatus()
        s._devList = getScsiDevices(s._osSysPath)

    def getDevices(s):
        s.update()
    #    for d in s._devList:
    #        print d
        devInfoList = []
        for dev in s._devList:
            devInfoList.append(dev.disp())
            
        return (s._devList, devInfoList)

    def swap(s): return s._swapStatus
    def mount(s): return s._mountStatus
    def dev(s): return s._devList

class SwapStatus:
    """Summary of active swap partitions or devices"""

    _swapData = None
    _devices = None

    def __init__(s):
        """Returns the output of the 'swapon -s' command, line by line"""
        text = callSysCommand(["swapon","-s"])
        s._swapData = text.replace("\t"," ").splitlines()
        # get a list of swap devices
        s._devices = []
        for line in s._swapData:
            lineList = line.split()
            if lineList[1] != "partition":
                continue
            s._devices.append(lineList[0])

    def isSwapDev(s, ioFile):
        if not s._devices or len(s._devices) < 1:
            return False
        resList = filter(strInList(ioFile), s._devices)
        if resList and len(resList) > 0:
            return True
        else:
            return False

class MountStatus:
    """Status of all the filesystems mounted in the system"""

    _mountData = None
    
    def __init__(s):
        """Returns the output of the 'mount' command, line by line"""
    # use /etc/mtab
    #    fn = os.path.join(os.sep,"etc","mtab")
    #    if not os.path.isfile(fn):
    #        return []
    #    fd = open(fn, 'r')
    #    rawData = fd.readlines()
    #    fd.close()
    #    data = map(removeLineBreak, rawData)
    #    print repr(data)
        text = callSysCommand(["mount"])
        s._mountData = text.splitlines()

    def getMountPoint(s, ioFile):
        if not s._mountData or len(s._mountData) < 1:
            return ""
        resList = filter(strInList(ioFile+" "), s._mountData)
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

class BlockDevice:

    _blkDevName = None
    _blkDevPath = None
    _ioFile = None
    _devNum = None
    _size = None
    _partitions = None # list of BlockDevices
    _holders = None    # list of BlockDevices
    _mountPoint = None

    def __init__(s, blkDevName, blkDevPath):
        if not os.path.isdir(blkDevPath):
            raise MyError("Block device path does not exist")
        s._blkDevName = blkDevName
        s._blkDevPath = os.path.realpath(blkDevPath) + os.sep
        s._size = getSize(blkDevPath)
        if s._size < 0:
            raise MyError("Could not determine block device size")
        s.getDeviceNumber()
        s._ioFile = getIoFilename(s._devNum)
        if not os.path.exists(s._ioFile):
            raise MyError("Could not find IO device path")
        # determine mount point
        s._mountPoint = status.mount().getMountPoint(s._ioFile)
        if s._mountPoint != "swap" and not os.path.isdir(s._mountPoint):
            s._mountPoint = None
        # get partitions eventually
        partitions = s.getSubDev(s._blkDevPath, s._blkDevName+"*")
        s._partitions = []
        addSubDevices(s._partitions, partitions, s._blkDevPath)
        # get holders eventually
        basePath = s._blkDevPath+"holders"+os.sep
        holders = s.getSubDev(basePath, "*")
        s._holders = []
        addSubDevices(s._holders, holders, basePath)
        # final verification
        if not s.isValid():
            raise MyError("Determined block device information not valid")

    def isInUse(s):
        if s._holders and len(s._holders) > 0:
            for h in s._holders:
                if h.isInUse():
                    return True
        if s._partitions and len(s._partitions) > 0:
            for p in s._partitions:
                if p.isInUse():
                    return True
        if s._mountPoint != None:
            return True
        return False

    def disp(s):
        dispList = [s.isInUse(), s._ioFile, s._mountPoint, s._size]
        # check holders for being in use
        holderList = []
        if s._holders and len(s._holders) > 0:
            for h in s._holders:
                holderList.append(h.disp())
        # check its partitions for being in use
        partList = []
        if s._partitions and len(s._partitions) > 0:
            for p in s._partitions:
                partList.append(p.disp())
        return (dispList, partList, holderList)

    def getSubDev(s, basePath, matchStr):
        """Returns a list of sub-devices (partitions and holders/dependents)"""
        if not s.isValid():
            return []
        entries = glob.glob(basePath + matchStr)
        if not entries: 
            return []
        # return a list of the holder names relative to the input block path
        relList = map(makeRel(basePath), entries)
        return relList

    def __str__(s):
        res = ""
        for attr in [s._blkDevName, s._ioFile, s._mountPoint, 
                     formatSize(s._size), s._devNum, s._blkDevPath]:
            res = res + str(attr) + " "

        global outputIndent
        outputIndent = outputIndent + "  "
        prefix = "\n" + outputIndent
        if s._holders:
            res = res + prefix + "[holders:]"
            for h in s._holders:
                res = res + prefix + str(h)
        elif s._partitions:
            res = res + prefix + "[partitions:]"
            for p in s._partitions:
                res = res + prefix + str(p)
        else:
            pass

        outputIndent = outputIndent[:-2]

        return res

    def isValid(s):
        return s._blkDevName and \
                os.path.isdir(s._blkDevPath) and \
                os.path.exists(s._ioFile) and \
                s._devNum > 0 and \
                s._size >= 0

    def getSysfsPath(s):
        if not s.isValid():
            return ""
        else:
            return s._blkDevPath

    def getDeviceNumber(s):
        if not s._devNum:
            fn = os.path.join(s._blkDevPath,"dev")
            if not os.path.isfile(fn):
                return -1
            (major, minor) = getLineFromFile(fn).split(":")
            if not major or not minor or major < 0 or minor < 0:
                return -1
            s._devNum = os.makedev(int(major), int(minor))
        return s._devNum

    def mount(s):
        """Mount block device"""
        # no partitions
        if len(s._partitions) == 0:
            if not s.isInUse():
                try:
                    res = callSysCommand(["truecrypt", "--mount", s._ioFile])
                except MyError, e:
                    print "failed to mount",s._ioFile,":",e
            else:
                raise DeviceInUseWarning()
        elif len(s._partitions) == 1:
            s._partitions[0].mount()
        else:
            pass # several partitions, which ? use exception

    def umount(s):
        """Unmount block device"""
        # no partitions
        if len(s._partitions) == 0:
            if len(s._holders) == 0:
                # do only for truecrypt devices
                isTruecrypt = strInList("truecrypt")
                if isTruecrypt(s._ioFile) and s._mountPoint:
                    try:
                        res = callSysCommand(["truecrypt", "-d", s._mountPoint])
                    except MyError, e:
                        print "failed to umount",s._ioFile,":",e
            elif len(s._holders) == 1:
                s._holders[0].umount()
            else:
                pass # several holders, what to do ?
        elif len(s._partitions) == 1:
            s._partitions[0].umount() # holders of this ?
        else:
            pass # several partitions, which ? use exception

def getSize(blockPath):
    """Returns the overall numerical size of a scsi block device.
    arg: absolute path to the scsi block device"""
    if not os.path.isdir(blockPath):
        return -1
    fn = os.path.join(blockPath, "size")
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
            dev = BlockDevice(devName, queryPath)
            if not dev.isValid():
                raise MyError("Not Valid")
        except MyError, e:
            print "Could not figure out block device ",devName,"->",e
        else:
            outList.append(dev)

### end BlockDevice related stuff

class ScsiDevice:
    _scsiAdr = None # list with <host> <channel> <id> <lun>
    _devPath = None # path to the scsi device descriptor
    _dev = None     # associated Block device object
    _driverName = None
    _vendor = None
    _model = None

    def blk(s): return s._dev

    def __init__(s, inPath, scsiStr):
        s._scsiAdr = scsiStr.split(":")
        s._devPath = os.path.realpath(os.path.join(inPath,scsiStr,"device"))
        if not os.path.isdir(s._devPath) or not s.isSupported():
            # throw exception here
            raise MyError("Device type not supported")
        (name, path) = getBlkDevPath(s._devPath)
        if not name or not path:
            # throw exception
            raise MyError("Could not determine block device path in /sys/")
        s._dev = BlockDevice(path, name)
        s.getDeviceDriver()
        s.getVendor()
        s.getModel()
        # final verification
        if not s.isValid():
            raise MyError("Determined Scsi device information not valid")

    def getModel(s):
        if s._model and len(s._model) > 0:
            return s._model
        s.model = ""
        fn = os.path.join(s._devPath,"model")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                s._model = txt
        return s._model

    def getVendor(s):
        if s._vendor and len(s._vendor) > 0:
            return s._vendor
        s._vendor = ""
        fn = os.path.join(s._devPath,"vendor")
        if os.path.isfile(fn):
            txt = getLineFromFile(fn)
            if len(txt) > 0:
                s._vendor = txt
        return s._vendor

    def getDeviceDriver(s):
        if s._driverName and len(s._driverName) > 0:
            return s._driverName
        sysfsPath = s._dev.getSysfsPath()
        if not os.path.isdir(sysfsPath):
            return ""
        path = os.path.realpath(os.path.join(sysfsPath,"device"))
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        (path,tail) = os.path.split(path)
        path = os.path.realpath(os.path.join(path,"driver"))
        (path,tail) = os.path.split(path)
        s._driverName = tail
        return s._driverName

    def isSupported(s):
        if not s._devPath or not os.path.isdir(s._devPath): 
            return False
        fn = os.path.join(s._devPath,"type")
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
        return len(s._scsiAdr) == 4 and \
                s._devPath and os.path.isdir(s._devPath) and \
                s._dev.isValid()
        # test for every blk device being valid

    def __str__(s):
        """Outputs full detailed information about this devices"""
        if not s.isValid():
            return "not valid!"
        output = str(s._scsiAdr) + \
                ", in use: " + str(s._dev.isInUse()) + \
                ", driver: " + str(s._driverName) + \
                ", vendor: " + str(s._vendor) + \
                ", model: " + str(s._model) + \
                "\n" + str(s._dev)
        return output

    def disp(s):
        """Outputs user-oriented information, less complete, data only"""
        if not s.isValid():
            return ([],[])
        subList = s._dev.disp()
        if not subList or len(subList) < 1 or len(subList[0]) < 1:
            return
        inUseStr = "[    ]"
        if subList[0][0]:
            inUseStr = "[used]"
        dev = ["["+reduce(lambda a, b: a+":"+b, s._scsiAdr)+"]", subList[0][0], s._model]
        return (dev,subList)

def getBlkDevPath(devPath):
    """Returns the scsi block device path.
    in:  path to the scsi device
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
def getIoFilename(devNum):
    """Search the block device filename in /dev/ based on the major/minor number"""
    if not devNum or devNum < 0:
        return ""
    # get all device files first
    for root, dirs, files in os.walk(Status._osDevPath):
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

def getScsiDevices(inPath):
    """Returns a list of scsi device descriptors including block devices"""
    if not os.path.isdir(inPath):
        return
    devs = []
    entries = os.listdir(inPath)
    for entry in entries:
        try:
            d = ScsiDevice(inPath, entry)
        except MyError, e:
            raise MyError("Init failed for "+entry+": "+e)
        else:
            if not d.isValid():
                raise MyError("Device not valid: "+entry)
            else:
                devs.append(d)
    return devs

### end ScsiDevice related stuff

status = Status()
