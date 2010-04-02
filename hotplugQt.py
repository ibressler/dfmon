"""Qt GUI for the hotplug manager
"""

# todo: fix devlist vs. blkdevlist

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mainwindow import Ui_MainWindow

import hotplugBackend
from hotplugBackend import formatSize, ScsiDevice, BlockDevice

InUseRole = Qt.UserRole

class MyItemDelegate(QItemDelegate):

    def __init__(s, parent = None):
        QItemDelegate.__init__(s, parent)
        print "init"

    def paint (s, painter, option, index):
        if not (QStyle.State_Selected & option.state):
            r = QRect(option.rect)
            r.setX(0)
            # test if item/device is in use
            if index.data(InUseRole).toBool():
                painter.setBrush(QColor(255, 0, 0, 32))
            else:
                painter.setBrush(QColor(0, 255, 0, 128))
            painter.setPen(Qt.lightGray)
            painter.drawRect(r)
        QItemDelegate.paint(s, painter, option, index)

class MyTreeWidgetItem(QTreeWidgetItem):
    def __init__(s, dev):
        QTreeWidgetItem.__init__(s, None)
        s.configureDevice(dev)

    def addBlockDevice(s, dev):
        if not dev: return
        item = MyTreeWidgetItem(dev)
        for part in dev.partitions():
            item.addBlockDevice(part)
        for holder in dev.holders():
            item.addBlockDevice(holder)
        s.addChild(item)
    
    def configureDevice(s, dev):
        if not dev: return
        # decide usage status
        toolTip = "[not used]"
        if dev.inUse():
            toolTip = "[in use]"
        # generate extended device type dependent info
        if dev.type() == ScsiDevice.Type:
            s.setText(0, dev.scsiStr())
            toolTip += " model: " + dev.model()
        elif dev.type() == BlockDevice.Type:
            s.setText(0, dev.ioFile())
            mp = dev.mountPoint()
            if len(mp): 
                toolTip += " mountpoint: '" + mp + "'"
            else:
                toolTip += " not mounted"
            toolTip += ", size: "+formatSize(dev.size())
        # finally set the extended info
        s.setToolTip(0, toolTip)
        s.setStatusTip(0, toolTip)
        s.setData(0, InUseRole, QVariant(dev.inUse())) # for the delegate
        if dev.type() == ScsiDevice.Type:
            s.addBlockDevice(dev.blk())

class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(s, parent = None):
        QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        delegate = MyItemDelegate(s.treeWidget.itemDelegate())
        s.treeWidget.setItemDelegate(delegate)
        s.treeWidget.setHeaderLabel("available devices")
        s.treeWidget.header().setDefaultAlignment(Qt.AlignHCenter)
        s.treeWidget.setMouseTracking(True)
#        r = qApp.desktop().screenGeometry()
#        print "screen width:", r.width(), "height:", r.height()
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for dev in devList:
            item = MyTreeWidgetItem(dev)
            rootItem.addChild(item)
        s.treeWidget.expandAll()

    def keyPressEvent(s, keyEvent):
        QMainWindow.keyPressEvent(s, keyEvent)
        if keyEvent.key() == Qt.Key_Escape:
            s.close()


# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
