"""Qt GUI for the hotplug manager
"""

# todo: fix devlist vs. blkdevlist

import sys
from PyQt4 import QtCore, QtGui
from mainwindow import Ui_MainWindow

import hotplugBackend

class MainWindow(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(s, parent=None):
        QtGui.QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList, devInfoList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for devInfo in devInfoList:
            #name = reduce(lambda a, b: a+", "+b, devInfo[0])
            item = QtGui.QTreeWidgetItem()
            configureItem(item, devInfo[0])
            addSubDeviceItems(item, devInfo[1])
            rootItem.addChild(item)
            if s.treeWidget.columnCount() < len(devInfo[0]):
                s.treeWidget.setColumnCount(len(devInfo[0]))
            print "count:", rootItem.childCount()

def configureItem(item, columnData):
    if not item or not columnData or len(columnData) <= 0:
        return
    col = 0
    for d in columnData:
        item.setText(col, str(d))
        col = col + 1

def addSubDeviceItems(rootItem, blkDevInfo):
    if not rootItem or not blkDevInfo or len(blkDevInfo) < 2:
        return
    item = QtGui.QTreeWidgetItem()
    configureItem(item, blkDevInfo[0])
    print "blkDevInfo:", blkDevInfo
    for partition in blkDevInfo[1]:
        addSubDeviceItems(item, partition)
    for holder in blkDevInfo[2]:
        addSubDeviceItems(item, holder)
    rootItem.addChild(item)
    print "count:", rootItem.childCount()

def qtMenu(argv):
    app = QtGui.QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
