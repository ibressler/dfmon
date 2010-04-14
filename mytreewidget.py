import time
import cPickle
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import hotplugBackend
from hotplugBackend import formatSize, formatTimeDistance

def tr(s):
    return QCoreApplication.translate(None, s)

class MyAction(QAction):

    def __init__(s, methodObj = None, text = "", parent = None):
        QAction.__init__(s, text, parent)
        s.methodObj = methodObj
        QObject.connect(s, SIGNAL("triggered(bool)"), s.triggerAction)

    def triggerAction(s, checked = False):
        if s.methodObj:
            QObject.emit(s, SIGNAL("triggered(QString, PyQt_PyObject)"), \
                                            s.text(), s.methodObj)

class IoThread(QThread):
    checkInterval = 500

    def __init__(s, parent = None):
        QThread.__init__(s, parent)

    def run(s):
        s.actionHandler = ActionHandler()
        s.timer = QTimer()
        s.timer.start(s.checkInterval)
        s.exec_()

    def stop(s):
        s.timer.stop()
        s.quit()

class ActionHandler(QObject):
    def doAction(s, text = "", methodObj = None):
        print "doAction pre"
        if not methodObj:
            return
        try:
            methodObj()
        except Exception, e:
            QObject.emit(s, SIGNAL("exception(QString, PyQt_PyObject)"), text, e)
        finally:
            QObject.emit(s, SIGNAL("actionDone(void)"))
        print "doAction post"

class MyTreeWidgetItem(QTreeWidgetItem):
    __dev = None # one element list (&reference ?)
    __overallChildCount = None
    __visibleChildCount = None

    def dev(s):
        return s.__dev[0]

#    def mountAction1(s, checked = False):
#        try:
#            s.dev().mount()
#        except hotplugBackend.DeviceInUseWarning, w:
#            QMessageBox.warning(s.treeWidget(), tr("Device in Use"), 
#                                tr("The selected device is already in use, I can't mount it."), 
#                                QMessageBox.Ok, QMessageBox.Ok)
#        except hotplugBackend.DeviceHasPartitionsWarning, w:
#            QMessageBox.warning(s.treeWidget(), tr("Device contains Partitions"), 
#                                tr("The selected device contains several partitions.\n")+
#                                tr("Please select one directly."), 
#                                QMessageBox.Ok, QMessageBox.Ok)
#        except hotplugBackend.MyError, e:
#            QMessageBox.critical(s.treeWidget(), tr("Mount Error"), 
#                                tr("Could not mount the selected device:\n")+str(e), 
#                                QMessageBox.Ok, QMessageBox.Ok)
#        finally:
#            # non-blocking action, start status monitor
#            s.treeWidget().startLastCmdMonitor()
#
#    def umountAction(s, checked = False):
#        try:
##            try:
#            s.dev().umount()
#        except hotplugBackend.MyError, e:
#            QMessageBox.critical(s.treeWidget(), tr("UnMount Error"), 
#                                tr("Could not unmount the selected device:\n")+str(e), 
#                                QMessageBox.Ok, QMessageBox.Ok)
#        finally:
#            # blocking action, done when reaching this
#            s.treeWidget().clear()
#
#    def removeAction(s, checked = False):
#        if not s.dev().isScsi(): return
#        tw = s.treeWidget()
#        try:
#                s.dev().remove()
#        except hotplugBackend.MyError, e:
#            QMessageBox.critical(s.treeWidget(), tr("Remove Error"), 
#                                tr("An error ocurred:\n")+str(e), 
#                                QMessageBox.Ok, QMessageBox.Ok)
#        finally:
#            # blocking action, done when reaching this
#            tw.clear()
#        if not s.dev().isValid():
#            QMessageBox.information(tw, tr("Success"), 
#                                tr("It is safe to unplug the device now."), 
#                                QMessageBox.Ok, QMessageBox.Ok)

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
    __ioThread = None

    def __init__(s, parent=None):
        QTreeWidget.__init__(s, parent)
        s.__ioThread = IoThread(s)
        # connect some signals/slots
        QObject.connect(s, SIGNAL("customContextMenuRequested(const QPoint&)"), s.contextMenu)
        QObject.connect(s, SIGNAL("itemCollapsed(QTreeWidgetItem *)"), s.itemCollapsedOrExpanded)
        QObject.connect(s, SIGNAL("itemExpanded(QTreeWidgetItem *)"), s.itemCollapsedOrExpanded)
        QObject.connect(s.__ioThread, SIGNAL("started(void)"), s.connectIoThread)
        s.__visibleRowCount = 0
        s.__ioThread.start()

    def closeEvent(s, event):
        s.__ioThread.stop()
        while not s.__ioThread.isFinished():
            s.__ioThread.wait()
        QTreeWidget.closeEvent(s, event)

    def connectIoThread(s):
        if s.__ioThread.isRunning():
            QObject.connect(s.__ioThread.actionHandler, 
                            SIGNAL("actionDone(void)"), 
                            s.refreshAction, Qt.QueuedConnection)
            QObject.connect(s.__ioThread.actionHandler, 
                            SIGNAL("exception(QString, PyQt_PyObject)"), 
                            s.actionExceptionHandler, Qt.QueuedConnection)
            QObject.connect(s.__ioThread.timer, SIGNAL("timeout(void)"), 
                            s.refreshActionIfNeeded, Qt.QueuedConnection)

#    def refreshLastCmd(s):
#        """Refreshes the tree after msecs milliseconds."""
#        if hotplugBackend.status.lastCmdStatusChanged():
#            s.refreshAction()
#            s.__timer.stop()
#
#    def startLastCmdMonitor(s):
#        s.__timer.start(1000)

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
            removeAction = MyAction(item.dev().remove, tr("umount all && remove"), menu)
            if s.__ioThread.isRunning():
                QObject.connect(removeAction, SIGNAL("triggered(QString, PyQt_PyObject)"), 
                            s.__ioThread.actionHandler.doAction, Qt.QueuedConnection)
            menu.addAction(removeAction)
        if item.dev().inUse():
            umountAction = MyAction(item.dev().umount, tr("umount"), menu)
            if s.__ioThread.isRunning():
                QObject.connect(umountAction, SIGNAL("triggered(QString, PyQt_PyObject)"), 
                            s.__ioThread.actionHandler.doAction, Qt.QueuedConnection)
            menu.addAction(umountAction)
        else: # not in use
            mountAction = MyAction(item.dev().mount, tr("mount with truecrypt"), menu)
            if s.__ioThread.isRunning():
                QObject.connect(mountAction, SIGNAL("triggered(QString, PyQt_PyObject)"), 
                            s.__ioThread.actionHandler.doAction, Qt.QueuedConnection)
            menu.addAction(mountAction)
        menu.addSeparator()
        refreshAction = QAction(tr("refresh all"), menu)
        QObject.connect(refreshAction, SIGNAL("triggered(bool)"), s.refreshAction)
        menu.addAction(refreshAction)
        # fix popup menu position
        pos = s.mapToGlobal(pos)
        pos.setY(pos.y() + s.header().sizeHint().height())
        menu.popup(pos)

    def actionExceptionHandler(s, text = "", e = None):
        if not e: return
        failureText = QString("Action '%1' failed: \n").arg(text)
        try:
            raise e
        except hotplugBackend.DeviceInUseWarning, w:
            QMessageBox.warning(s, tr("Device in Use"), 
                                failureText+
                                tr("The selected device is already in use."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.DeviceHasPartitionsWarning, w:
            QMessageBox.warning(s, tr("Device contains Partitions"), 
                                failureText+
                                tr("The selected device contains several partitions.\n")+
                                tr("Please select one directly."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.MyError, e:
            QMessageBox.critical(s, tr("An Error Occurred"), 
                                failureText+
                                str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except hotplugBackend.RemovalSuccessInfo, e:
            QMessageBox.information(s, tr("Success"), 
                    tr("It is safe to unplug the device now."), 
                    QMessageBox.Ok, QMessageBox.Ok)

    def refreshActionIfNeeded(s, checked = False):
        if hotplugBackend.status.devStatusChanged() \
        or hotplugBackend.status.mountStatusChanged():
            # wait a moment after change detected 
            # (let the system create device files, etc..)
            QTimer.singleShot(s.__ioThread.checkInterval, s.refreshAction)

    def refreshAction(s, checked = False):
        print "refreshAction"
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
