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
    __dev = None # one element list (&reference ?)

    def dev(s):
        return s.__dev[0]

    def mountAction(s, checked = False):
        print "MyTreeWidgetItem.mountAction:", s.dev().fullName()
        try:
            if s.dev().isBlock(): 
                s.dev().mount()
            elif s.dev().isScsi(): 
                s.dev().blk().mount()
        except hotplugBackend.DeviceInUseWarning, w:
            QMessageBox.warning(s.treeWidget(), "Device in Use", \
                                "The selected device is already in use, I can't mount it.", \
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.DeviceHasPartitions, w:
            QMessageBox.warning(s.treeWidget(), "Device contains Partitions", \
                                "The selected device contains several partitions.\n"+\
                                "Please select one directly.", \
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s.treeWidget(), "Mount Error", \
                                "Could not mount the selected device:\n"+str(e), \
                                QMessageBox.Ok, QMessageBox.Ok)

    # setup methods

    def __init__(s, dev):
        QTreeWidgetItem.__init__(s, None)
        #s.__dev = dev # this produces cascaded instance duplication somehow
        # don't want to copy the complete Device incl. sublists
        s.__dev = [dev]
        s.configure()

    def addBlockDevice(s, dev):
        if not dev: return
        item = MyTreeWidgetItem(dev)
        for part in dev.partitions():
            item.addBlockDevice(part)
        for holder in dev.holders():
            item.addBlockDevice(holder)
        s.addChild(item)

    def configure(s):
        if not s.dev(): return
        s.setText(0, s.dev().shortName())
        # decide usage status
        toolTip = "[not used]"
        if s.dev().inUse():
            toolTip = "[in use]"
        statusTip = toolTip
        # generate extended device type dependent info
        toolTip += " " + s.dev().fullName()
        if s.dev().isBlock():
            if s.dev().inUse():
                mp = s.dev().mountPoint()
                if len(mp): 
                    toolTip += " [mountpoint: " + mp + "]"
                else:
                    toolTip += " [not mounted]"
            sizeStr = " size: "+formatSize(s.dev().size())
            toolTip += sizeStr
            statusTip += sizeStr
        elif s.dev().isScsi():
            statusTip += " " + s.dev().model()
        # finally set the extended info
        s.setToolTip(0, toolTip)
        s.setStatusTip(0, statusTip)
        s.setData(0, InUseRole, QVariant(s.dev().inUse())) # for the delegate
        if s.dev().isScsi():
            s.addBlockDevice(s.dev().blk())

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
        rootItem = s.treeWidget.invisibleRootItem()
        for dev in hotplugBackend.status.getDevices():
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
