"""Qt GUI for the hotplug manager
"""

# todo: fix devlist vs. blkdevlist

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mainwindow import Ui_MainWindow

import hotplugBackend
from hotplugBackend import formatSize

class MainWindow(QMainWindow, Ui_MainWindow):
    _columnCount = None

    def __init__(s, parent=None):
        QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for dev in devList:
            #name = reduce(lambda a, b: a+", "+b, devInfo[0])
            item = QTreeWidgetItem()
            configScsiDevice(item, dev)
            addBlockDevice(item, dev.blk())
            rootItem.addChild(item)
        s.treeWidget.setColumnCount(4)
        s.treeWidget.expandAll()
#        width = 0
#        for col in range(0, s.treeWidget.columnCount()):
##            s.treeWidget.resizeColumnToContents(col)
#            width += s.treeWidget.columnWidth(col)
#            print "colSH:", s.treeWidget.header().sectionSizeHint(col)
#            print "c",col,"sizeHintForColumn:", str(s.treeWidget.sizeHintForColumn(col))
#            print "mode:", str(s.treeWidget.header().resizeMode(col))
#        s.treeWidget.header().resizeSections(QHeaderView.ResizeToContents)
#        print "test", s.treeWidget.header().width()
#        print "mw, size:", str(s.size().width()), "sizeHint:", str(s.sizeHint().width())
#        print "tw, size:", str(s.treeWidget.size().width()), "sizeHint:", str(s.treeWidget.sizeHint().width())
#        print "calc width:", width, "tw width:", s.treeWidget.width(), "vis:", s.treeWidget.viewport().width()
#        mwSize = s.sizeHint()
#        margin = mwSize.width() - s.treeWidget.sizeHint().width()
#        print "margin:", margin
#        margin += s.treeWidget.verticalScrollBar().width()
#        print "margin:", margin
#        mwSize.setWidth(width+margin)
#        print "new width:", mwSize.width()
        #s.resize(mwSize)

def addBlockDevice(rootItem, dev):
    if not rootItem or not dev: return
    item = QTreeWidgetItem()
    configBlockDevice(item, dev)
    for part in dev.partitions():
        addBlockDevice(item, part)
    for holder in dev.holders():
        addBlockDevice(item, holder)
    rootItem.addChild(item)

def configScsiDevice(item, dev):
    if not item or not dev: 
        return
    item.setText(0, dev.scsiStr()+" "+dev.model())
    item.setText(1, str(dev.inUse()))

def configBlockDevice(item, dev):
    if not item or not dev: return
    col = 0
    for s in dev.ioFile(), str(dev.inUse()), dev.mountPoint(), formatSize(dev.size()):
        item.setText(col, s)
        col = col + 1
    item.setTextAlignment(col-1, Qt.AlignRight)

# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
