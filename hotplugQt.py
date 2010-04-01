"""Qt GUI for the hotplug manager
"""

# todo: fix devlist vs. blkdevlist

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mainwindow import Ui_MainWindow

import hotplugBackend
from hotplugBackend import formatSize

class MyItemDelegate(QItemDelegate):

    def __init__(s, parent = None):
        QItemDelegate.__init__(s, parent)
        print "init"

    def paint (s, painter, option, index):
        r = QRect(option.rect)
        r.setX(0)
        if index.row() % 2:
            painter.setBrush(QColor(255, 0, 0, 64))
        else:
            painter.setBrush(QColor(0, 255, 0, 64))
        painter.setPen(Qt.lightGray)
        painter.drawRect(r)
        QItemDelegate.paint(s, painter, option, index)

class MainWindow(QMainWindow, Ui_MainWindow):
    _columnCount = None

    def __init__(s, parent = None):
        QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        delegate = MyItemDelegate(s.treeWidget.itemDelegate())
        s.treeWidget.setItemDelegate(delegate)
        s.treeWidget.setHeaderLabel("available devices")
        s.treeWidget.header().setDefaultAlignment(Qt.AlignHCenter)
#        r = qApp.desktop().screenGeometry()
#        print "screen width:", r.width(), "height:", r.height()
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for dev in devList:
            item = QTreeWidgetItem()
            configScsiDevice(item, dev)
            addBlockDevice(item, dev.blk())
            rootItem.addChild(item)
        s.treeWidget.expandAll()
        
    def keyPressEvent(s, keyEvent):
        QMainWindow.keyPressEvent(s, keyEvent)
        if keyEvent.key() == Qt.Key_Escape:
            s.close()

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
    item.setText(0, dev.scsiStr())
    toolTip = "not used"
    if dev.inUse():
#        item.setBackground(0, Qt.lightGray)
        toolTip = "in use"
    toolTip += ", model: " + dev.model()
    item.setToolTip(0, toolTip)

def configBlockDevice(item, dev):
    if not item or not dev: return
    item.setText(0, dev.ioFile())
    toolTip = "not used"
    if dev.inUse():
#        item.setBackground(0, Qt.lightGray)
        toolTip = "in use"
    mp = dev.mountPoint()
    if len(mp): 
        toolTip += ", mountpoint: '" + mp + "'"
    else:
        toolTip += ", not mounted"
    toolTip += ", size: "+formatSize(dev.size())
    item.setToolTip(0, toolTip)

# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
