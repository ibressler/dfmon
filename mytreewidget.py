from PyQt4.QtCore import *
from PyQt4.QtGui import *
import hotplugBackend
from hotplugBackend import formatSize

def tr(s):
   return QCoreApplication.translate(None, s)

class MyTreeWidgetItem(QTreeWidgetItem):
    __dev = None # one element list (&reference ?)

    def dev(s):
        return s.__dev[0]

    def mountAction(s, checked = False):
        try:
                s.dev().mount()
        except hotplugBackend.DeviceInUseWarning, w:
            QMessageBox.warning(s.treeWidget(), tr("Device in Use"), 
                                tr("The selected device is already in use, I can't mount it."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.DeviceHasPartitions, w:
            QMessageBox.warning(s.treeWidget(), tr("Device contains Partitions"), 
                                tr("The selected device contains several partitions.\n")+
                                tr("Please select one directly."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s.treeWidget(), tr("Mount Error"), 
                                tr("Could not mount the selected device:\n")+str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        finally:
            s.treeWidget().clear()

    def umountAction(s, checked = False):
        try:
                s.dev().umount()
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s.treeWidget(), tr("UnMount Error"), 
                                tr("Could not unmount the selected device:\n")+str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        finally:
            s.treeWidget().clear()

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
        toolTip = "["+tr("not used")+"]"
        if s.dev().inUse():
            toolTip = "["+tr("in use")+"]"
        statusTip = ""+toolTip
        # generate extended device type dependent info
        toolTip += " " + s.dev().fullName()
        if s.dev().isBlock():
            if s.dev().inUse():
                mp = s.dev().mountPoint()
                if len(mp): 
                    toolTip += " ["+tr("mountpoint")+": " + mp + "]"
                else:
                    toolTip += " ["+tr("not mounted")+"]"
            sizeStr = " "+tr("size")+": "+formatSize(s.dev().size())
            toolTip += sizeStr
            statusTip += sizeStr
        # finally set the extended info
        s.setToolTip(0, toolTip)
        s.setStatusTip(0, statusTip)
        s.setData(0, Qt.UserRole, QVariant(s.dev().inUse())) # for the delegate
        if s.dev().isScsi():
            s.addBlockDevice(s.dev().blk())

class MyTreeWidget(QTreeWidget):

    def __init__(s, parent=None):
        QTreeWidget.__init__(s, parent)
        # connect some signals/slots
        QObject.connect(s, SIGNAL("customContextMenuRequested(const QPoint&)"), s.contextMenu)
        s.clear() # clears and rebuilds the tree

    def sizeHint(s):
        """Show all columns (no horizontal scrollbar)"""
        widthHint = 0
        for col in range(0, s.columnCount()):
            colWidth = s.sizeHintForColumn(col)
            colWidth += 5
            s.header().resizeSection(col, colWidth)
            widthHint += colWidth + 2 # magic margin between columns
        widthHint += 2
        if not s.verticalScrollBar().isHidden():
            widthHint += s.verticalScrollBar().width()
        hint = QTreeWidget.sizeHint(s)
        hint.setWidth(widthHint)
        hint.setHeight(300)
        return hint

    def contextMenu(s, pos):
        item = s.itemAt(pos)
        menu = QMenu(s)
        mountAction = QAction(tr("mount with truecrypt"), menu)
        QObject.connect(mountAction, SIGNAL("triggered(bool)"), item.mountAction)
        umountAction = QAction(tr("umount"), menu)
        QObject.connect(umountAction, SIGNAL("triggered(bool)"), item.umountAction)
        menu.addAction(mountAction)
        menu.addAction(umountAction)
        # fix popup menu position
        pos = s.mapToGlobal(pos)
        pos.setY(pos.y() + s.header().sizeHint().height())
        menu.popup(pos)
        
    def reset(s):
        QTreeWidget.reset(s)
        rootItem = s.invisibleRootItem()
        for dev in hotplugBackend.status.getDevices():
            item = MyTreeWidgetItem(dev)
            rootItem.addChild(item)
        s.expandAll()
