# mytreewidget.py
#
# This file is part of dfmon.
#
# dfmon is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# dfmon is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with dfmon.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Ingo Bressler (April 2010)

"""QTreeWidget subclass for the tree structure of the Qt-GUI of dfmon.

Initial motivation was a custom sizeHint (fixed to fit the content).
But also data access (Scsi- and BlockDevice) and action processing is 
implemented here.
"""

import time
import cPickle
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import dfmonBackend
from dfmonBackend import formatSize, formatTimeDistance

def tr(s): # translation shortcut
    return QCoreApplication.translate(None, s)

class MyAction(QAction):
    """Forwards the associated method (object)."""

    def __init__(s, methodObj = None, text = "", parent = None):
        QAction.__init__(s, text, parent)
        s.methodObj = methodObj
        QObject.connect(s, SIGNAL("triggered(bool)"), s.triggerAction)

    def triggerAction(s, checked = False):
        if s.methodObj:
            QObject.emit(s, SIGNAL("triggered(QString, PyQt_PyObject)"), \
                                            s.text(), s.methodObj)

class IoThread(QThread):
    """Runs device actions (system commands) in the background and polls 
    for status changes."""
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
    """Executes an action on a certain device (methodObj)."""
    def doAction(s, text = "", methodObj = None):
#        print "doAction pre"
        if not methodObj:
            return
        try:
            methodObj()
        except Exception, e:
            QObject.emit(s, SIGNAL("exception(QString, PyQt_PyObject)"), text, e)
        finally:
            QObject.emit(s, SIGNAL("actionDone(void)"))
#        print "doAction post"

class MyTreeWidgetItem(QTreeWidgetItem):
    """An item (row) in the GUI device tree. Has an associated device and 
    keeps track of the existing and visible children of a node."""
    __dev = None # one element list (&reference ?)
    __overallChildCount = None
    __visibleChildCount = None

    def dev(s):
        return s.__dev[0]

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
            curtime = int(time.time())
            ts = s.dev().timeStamp()
            dist = curtime - ts
            if dist > 0:
                toolTip += tr(" (added %1 ago)").arg(formatTimeDistance(dist))
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
        # why do I still get: "QThread: Destroyed while thread is still running"
        QTreeWidget.closeEvent(s, event)

    def connectIoThread(s):
        if s.__ioThread.isRunning():
            QObject.connect(s.__ioThread.actionHandler, 
                            SIGNAL("actionDone(void)"), 
                            s.refreshAction, Qt.QueuedConnection)
            QObject.connect(s.__ioThread.actionHandler, 
                            SIGNAL("exception(QString, PyQt_PyObject)"), 
                            s.exceptionHandler, Qt.QueuedConnection)
            QObject.connect(s.__ioThread.timer, SIGNAL("timeout(void)"), 
                            s.refreshActionIfNeeded, Qt.QueuedConnection)

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

    def exceptionHandler(s, text = "", e = None):
        if not e: return
        failureText = QString("Action '%1' failed: \n").arg(text)
        try:
            raise e
        except dfmonBackend.DeviceInUseWarning, w:
            QMessageBox.warning(s, tr("Device in Use"), 
                                failureText+
                                tr("The selected device is already in use."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except dfmonBackend.DeviceHasPartitionsWarning, w:
            QMessageBox.warning(s, tr("Device contains Partitions"), 
                                failureText+
                                tr("The selected device contains several partitions.\n")+
                                tr("Please select one directly."), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except dfmonBackend.MyError, e:
            QMessageBox.critical(s, tr("An Error Occurred"), 
                                failureText+
                                str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)
        except dfmonBackend.RemovalSuccessInfo, e:
            QMessageBox.information(s, tr("Success"), 
                    tr("It is safe to unplug the device now."), 
                    QMessageBox.Ok, QMessageBox.Ok)

    def refreshActionIfNeeded(s, checked = False):
        if dfmonBackend.status.devStatusChanged() \
        or dfmonBackend.status.mountStatusChanged():
            # wait a moment after change detected 
            # (let the system create device files, etc..)
            # sometimes, an exception occurs here (for 500ms delay):
            # "Could not find IO device path" BlockDevice.__init__()
            QTimer.singleShot(int(2*s.__ioThread.checkInterval), s.refreshAction)

    def refreshAction(s, checked = False):
        """Updates items as needed"""
# add recursive __eq__/__ne__ to Scsi/BlockDevice
# get status, compare new devices with those in the tree
# if name is the same, remove and add new one at same position
# otherwise remove obsolete items, add new ones on top (ignore time -> bus reset)
#        print "refreshAction"
#        rootItem = s.invisibleRootItem()
#        for i in range(0, rootItem.childCount()):
#            print rootItem.child(i).text(0)
        s.clear()

    def reset(s):
        """Deletes all items and rebuild the tree"""
        QTreeWidget.reset(s)
        rootItem = s.invisibleRootItem()
        try:
            for dev in dfmonBackend.status.getDevices():
#                print "dev:", dev.scsiStr()
                item = MyTreeWidgetItem(dev)
                rootItem.addChild(item)
                item.expandAll()
        except Exception, e:
            s.exceptionHandler(tr("refresh"), e)
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
