"""Qt GUI for the hotplug manager
"""

# todo: fix devlist vs. blkdevlist

import sys
from PyQt4 import QtCore, QtGui
from mainwindow import Ui_MainWindow

import hotplugBackend
from hotplugBackend import formatSize

class MainWindow(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(s, parent=None):
        QtGui.QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for dev in devList:
            #name = reduce(lambda a, b: a+", "+b, devInfo[0])
            item = QtGui.QTreeWidgetItem()
            configScsiDevice(item, dev)
            addBlockDevice(item, dev.blk())
            rootItem.addChild(item)
            s.treeWidget.setColumnCount(4)

def configScsiDevice(item, dev):
    if not item or not dev: return
    col = 0
    for s in dev.model(), dev.scsiStr(), str(dev.inUse()):
        item.setText(col, s)
        col = col + 1

def configBlockDevice(item, dev):
    if not item or not dev: return
    col = 0
    for s in dev.ioFile(), str(dev.inUse()), dev.mountPoint(), formatSize(dev.size()):
        item.setText(col, s)
        col = col + 1

def addBlockDevice(rootItem, dev):
    if not rootItem or not dev: return
    item = QtGui.QTreeWidgetItem()
    configBlockDevice(item, dev)
    for part in dev.partitions():
        addBlockDevice(item, part)
    for holder in dev.holders():
        addBlockDevice(item, holder)
    rootItem.addChild(item)

def qtMenu(argv):
    app = QtGui.QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
