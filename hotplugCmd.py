
import time
import hotplugBackend
from hotplugBackend import MyError, DeviceInUseWarning, removeLineBreak

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

def formatBlkInfo(blkInfo, lvl, prefix):
    if not blkInfo or len(blkInfo) <= 0 or len(blkInfo[0]) < 2:
        return []
    line = []
    # add recursion depth dependent prefix
    o = ""
    for i in range(0,lvl): o = o+" "
    # add the description of a single device
    o = o + prefix + str(blkInfo[0][1])
    line.append(o) # first column
    # add usage status
    if blkInfo[0][0]:
        line.append("[used]")
    else:
        line.append("[    ]")
    for i in range(2,len(blkInfo[0])-1): # middle columns
            line.append(str(blkInfo[0][i]))
    line.append(formatSize(blkInfo[0][-1])) # last column
    res = []
    res.append(line) # output is list of lines (which are column lists)
    # add sub devices recursive
    lvl = lvl + len(prefix)
    for part in blkInfo[1]:
        res.extend(formatBlkInfo(part, lvl, prefix))
    for holder in blkInfo[2]:
        res.extend(formatBlkInfo(holder, lvl, prefix))
    lvl = lvl - len(prefix)
    return res

def printTable(listArr):
    """prints a table with optimal column width"""
    colWidth = []
    # determine optimal width of each column
    for col in range(0,len(listArr[0])):
        maxWidth = 0
        for row in range(0,len(listArr)):
            width = len(listArr[row][col])
            if width > maxWidth:
                maxWidth = width
        colWidth.append(maxWidth)
    o = ""
    for row in listArr:
        if len(o) > 0: o = o + "\n"
        for col, width in zip(row, colWidth)[:-1]:
            o = o + "%-*s " % ( width, col )
        o = o + "%*s " % ( colWidth[-1], row[-1] )

    return o

def printBlkInfo(blkInfo):
    return printTable(formatBlkInfo(blkInfo, 1, "'> "))

def getStatus():
    hotplugBackend.status.update()
    devList = hotplugBackend.status.dev()
#    for d in devList:
#        print d
    devInfoList = []
    for dev in devList:
        devInfoList.append(dev.disp())

    i = 0
    for devInfo in devInfoList:
        out = "("+str(i) + ")\t"
        for d in devInfo[0]:
            out = out + d + "\t"
        if i > 0:
            out = "\n" + out
            for k in range(0,len(out)): out = "-" + out
        print out
        print printBlkInfo(devInfo[1])
        i = i + 1

    return (devList, devInfoList)

def consoleMenu():
    try:
        devList, devInfoList = getStatus()
    except MyError, e:
        print "Error initializing system status: ",e
    else:
        input = removeLineBreak(raw_input("\n=> Select a device ('q' for quit): "))
        if input != "q" and input.isdigit():
            d = int(input)
            if d < 0: d = 0
            if d >= len(devList): d = len(devList)
            print "selected device:",input,"\n",printBlkInfo(devInfoList[d][1])
            try:
                devList[d].blk().mount()
            except DeviceInUseWarning:
                input = removeLineBreak(raw_input("\n=> Selected device is in use, unmount ? [Yn] "))
                if len(input) == 0:
                    devList[d].blk().umount()
        else:
            print "aborted."
    
        time.sleep(1.0)
        getStatus()
        return 0
