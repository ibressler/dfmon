import time
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import hotplugBackend
from hotplugBackend import formatSize, formatTimeDistance

def tr(s):
   return QCoreApplication.translate(None, s)

class MyTreeWidgetItem(QTreeWidgetItem):
    __dev = None # one element list (&reference ?)
    __overallChildCount = None
    __visibleChildCount = None

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
            # non-blocking action, start status monitor
            s.treeWidget().startLastCmdMonitor()

    def umountAction(s, checked = False):
        try:
                s.dev().umount()
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s.treeWidget(), tr("UnMount Error"), 
                                tr("Could not unmount the selected device:\n")+str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        finally:
            # blocking action, done when reaching this
            s.treeWidget().clear()

    def removeAction(s, checked = False):
        if not s.dev().isScsi(): return
        tw = s.treeWidget()
        try:
                s.dev().remove()
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s.treeWidget(), tr("Remove Error"), 
                                tr("An error ocurred:\n")+str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        finally:
            # blocking action, done when reaching this
            tw.clear()
        if not s.dev().isValid():
            QMessageBox.information(tw, tr("Success"), 
                                tr("It is safe to unplug the device now."), 
                                QMessageBox.Ok, QMessageBox.Ok)

    # setup methods

    def __init__(s, dev):
        QTreeWidgetItem.__init__(s, None)
        #s.__dev = dev # this produces cascaded instance duplication somehow
        # don't want to copy the complete Device incl. sublists
        s.__dev = [dev]
        s.__overallChildCount = 0
        s.__visibleChildCount = 0
        s.configure()

    def expanded(s):
        s.__visibleChildCount = s.childCount()
        for i in range(0, s.childCount()):
            s.__visibleChildCount += s.child(i).visibleChildCount()
        if s.parent():
            s.parent().expanded()

    def collapsed(s):
        s.__visibleChildCount = 0
        if s.parent():
            s.parent().expanded()

    def addBlockDevice(s, dev):
        if not dev: return
        item = MyTreeWidgetItem(dev)
        for part in dev.partitions():
            item.addBlockDevice(part)
        for holder in dev.holders():
            item.addBlockDevice(holder)
        s.addChild(item)
        s.__overallChildCount += 1 + item.overallChildCount()

    def configure(s):
        if not s.dev(): return
        s.setText(0, s.dev().shortName())
        # decide usage status
        toolTip = tr("[not used]")
        if s.dev().inUse():
            toolTip = tr("[in use]")
        statusTip = ""+toolTip
        # generate extended device type dependent info
        toolTip += " " + s.dev().fullName()
        if s.dev().isBlock():
            if s.dev().inUse():
                mp = s.dev().mountPoint()
                if len(mp): 
                    toolTip += tr(" [mountpoint: %1]").arg(mp)
                else:
                    toolTip += tr(" [not mounted]")
            sizeStr = tr(" size: %1").arg(formatSize(s.dev().size()))
            toolTip += sizeStr
            statusTip += sizeStr
        elif s.dev().isScsi():
            statusTip += " " + s.dev().model()
            secs = int(time.time()) - s.dev().timeStamp()
            toolTip += tr(" (added %1 ago)").arg(formatTimeDistance(secs))
        # finally set the extended info
        s.setToolTip(0, toolTip)
        s.setStatusTip(0, statusTip)
        s.setData(0, Qt.UserRole, QVariant(s.dev().inUse())) # for the delegate
        if s.dev().isScsi():
            s.addBlockDevice(s.dev().blk())

    def overallChildCount(s):
        """Returns the recursive child count."""
        return s.__overallChildCount

    def visibleChildCount(s):
        """Returns the recursive child count."""
        return s.__visibleChildCount

    def expandAll(s):
        s.setExpanded(True)
        for i in range(0, s.childCount()):
            s.child(i).setExpanded(True)
            s.child(i).expandAll()

class MyTreeWidget(QTreeWidget):
    __visibleRowCount = None # overall count of rows
    __timer = None

    def __init__(s, parent=None):
        QTreeWidget.__init__(s, parent)
        s.__timer = QTimer(s)
        # connect some signals/slots
        QObject.connect(s, SIGNAL("customContextMenuRequested(const QPoint&)"), s.contextMenu)
        QObject.connect(s, SIGNAL("itemCollapsed(QTreeWidgetItem *)"), s.itemCollapsedOrExpanded)
        QObject.connect(s, SIGNAL("itemExpanded(QTreeWidgetItem *)"), s.itemCollapsedOrExpanded)
        QObject.connect(s.__timer, SIGNAL("timeout(void)"), s.refreshLastCmd)
        s.__visibleRowCount = 0

    def refreshLastCmd(s):
        """Refreshes the tree after msecs milliseconds."""
        if hotplugBackend.status.lastCmdStatusChanged():
            s.refreshAction()
            s.__timer.stop()

    def startLastCmdMonitor(s):
        s.__timer.start(1000)

    def sizeHint(s):
        """Show all entries so that no scrollbar is required"""
        # sum up all column widths
        widthHint = s.sizeHintForColumn(0) + 5 # arbitrary margin for beautification
        # consider the header width
        if widthHint < s.header().sizeHint().width():
            widthHint = s.header().sizeHint().width() + 2*2
        # consider the scrollbar width
        if s.verticalScrollBar().isVisible():
            widthHint += s.verticalScrollBar().width()
        # update the current/original size hint
        hint = QTreeWidget.sizeHint(s)
        hint.setWidth(widthHint)
        # set height according to # rows
        h = s.indexRowSizeHint(s.indexFromItem(s.invisibleRootItem().child(0))) # one row
        heightHint = s.__visibleRowCount * h + s.header().height() + 2*2 # magic margin 2+2
        # stay within desktop area
        desktop = qApp.desktop()
        maxHeight = desktop.availableGeometry(desktop.screenNumber(s)).height()
        if heightHint > maxHeight:
            heightHint = maxHeight
        hint.setHeight(heightHint)
        return hint

    def contextMenu(s, pos):
        item = s.itemAt(pos)
        menu = QMenu(s)
        if item.dev().isScsi():
            removeAction = QAction(tr("umount all && remove"), menu)
            QObject.connect(removeAction, SIGNAL("triggered(bool)"), item.removeAction)
            menu.addAction(removeAction)
        if item.dev().inUse():
            umountAction = QAction(tr("umount"), menu)
            QObject.connect(umountAction, SIGNAL("triggered(bool)"), item.umountAction)
            menu.addAction(umountAction)
        else: # not in use
            mountAction = QAction(tr("mount with truecrypt"), menu)
            QObject.connect(mountAction, SIGNAL("triggered(bool)"), item.mountAction)
            menu.addAction(mountAction)
        menu.addSeparator()
        refreshAction = QAction(tr("refresh all"), menu)
        QObject.connect(refreshAction, SIGNAL("triggered(bool)"), s.refreshAction)
        menu.addAction(refreshAction)
        # fix popup menu position
        pos = s.mapToGlobal(pos)
        pos.setY(pos.y() + s.header().sizeHint().height())
        menu.popup(pos)

    def refreshAction(s, checked = False):
        s.clear()

    def reset(s):
        QTreeWidget.reset(s)
        rootItem = s.invisibleRootItem()
        for dev in hotplugBackend.status.getDevices():
            item = MyTreeWidgetItem(dev)
            rootItem.addChild(item)
            item.expandAll()
        s.setVisibleRowCount()
        QObject.emit(s, SIGNAL("contentChanged(void)"))

    def itemCollapsedOrExpanded(s, item):
        if item.isExpanded():
            item.expanded()
        else: # collapsed
            item.collapsed()
        s.setVisibleRowCount()
        QObject.emit(s, SIGNAL("contentChanged(void)"))

    def setVisibleRowCount(s):
        rootItem = s.invisibleRootItem()
        s.__visibleRowCount = rootItem.childCount()
        for i in range(0, rootItem.childCount()):
            s.__visibleRowCount += rootItem.child(i).visibleChildCount()
