# -*- coding: utf-8 -*-
# mytreewidget.py
#
# Copyright (c) 2010-2011, Ingo Breßler <dfmon@ingobressler.net>
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

"""
QTreeWidget subclass for the tree structure of the Qt-GUI of dfmon.

Initial motivation was a custom sizeHint (fixed to fit the content).
But also data access (Scsi- and BlockDevice) and action processing is 
implemented here.
"""

import time
from PyQt4.QtCore import (QObject, QCoreApplication, SIGNAL, QThread, Qt,
                          QVariant, QTimer, QString)
from PyQt4.QtGui import (QAction, QTreeWidgetItem, QTreeWidget, QLineEdit,
                         QInputDialog, QMenu, QMessageBox)
import backend
from backend import formatSize, formatTimeDistance
import traceback

def tr(s): # translation shortcut
    return QCoreApplication.translate(None, s)

class MyAction(QAction):
    """Forwards the associated method (object)."""

    def __init__(self, methodObj = None, text = "", parent = None):
        QAction.__init__(self, text, parent)
        self.methodObj = methodObj
        QObject.connect(self, SIGNAL("triggered(bool)"), self.triggerAction)

    def triggerAction(self, checked = False):
        if self.methodObj:
            QObject.emit(self, SIGNAL("triggered(QString, PyQt_PyObject)"),
                                            self.text(), self.methodObj)

class IoThread(QThread):
    """Runs device actions (system commands) in the background"""

    def __init__(self, parent = None):
        QThread.__init__(self, parent)

    def run(self):
        self.actionHandler = ActionHandler()
        backend.STATUS.sudoPwdFct = self.actionHandler.emitPwdSignal
        self.exec_()

class ActionHandler(QObject):
    """Executes an action on a certain device (methodObj)."""
    def doAction(self, text = "", methodObj = None):
#        print "doAction pre"
        if not methodObj:
            return
        try:
            methodObj()
        except Exception, e:
            QObject.emit(self, SIGNAL("exception(QString, PyQt_PyObject)"),
                         text, e)
        finally:
            QObject.emit(self, SIGNAL("actionDone(void)"))

    def emitPwdSignal(self):
        resList = [""]
        QObject.emit(self, SIGNAL("passwordDialog(PyQt_PyObject)"), resList)
        return str(resList[0])

class MyTreeWidgetItem(QTreeWidgetItem):
    """An item (row) in the GUI device tree. Has an associated device and 
    keeps track of the existing and visible children of a node."""
    _dev = None # one element list (&reference ?)
    _overallChildCount = None
    _visibleChildCount = None

    def dev(self):
        return self._dev[0]

    # setup methods

    def __init__(self, dev):
        QTreeWidgetItem.__init__(self, None)
        #self._dev = dev # this produces cascaded instance duplication somehow
        # don't want to copy the complete Device incl. sublists
        self._dev = [dev]
        self._overallChildCount = 0
        self._visibleChildCount = 0
        self.configure()

    def expanded(self):
        self._visibleChildCount = self.childCount()
        for i in range(0, self.childCount()):
            self._visibleChildCount += self.child(i).visibleChildCount()
        if self.parent():
            self.parent().expanded()

    def collapsed(self):
        self._visibleChildCount = 0
        if self.parent():
            self.parent().expanded()

    def addBlockDevice(self, dev):
        if not dev:
            return
        item = MyTreeWidgetItem(dev)
        for part in dev.partitions():
            item.addBlockDevice(part)
        for holder in dev.holders():
            item.addBlockDevice(holder)
        self.addChild(item)
        self._overallChildCount += 1 + item.overallChildCount()

    def configure(self):
        if not self.dev():
            return
        self.setText(0, self.dev().shortName())
        # decide usage status
        toolTip = tr("[not used]")
        if self.dev().inUse():
            toolTip = tr("[in use]")
        statusTip = ""+toolTip
        # generate extended device type dependent info
        toolTip += " " + self.dev().fullName()
        if self.dev().isBlock():
            if self.dev().inUse():
                mp = self.dev().mountPoint()
                if len(mp): 
                    toolTip += tr(" [mountpoint: %1]").arg(mp)
                else:
                    toolTip += tr(" [not mounted]")
            sizeStr = tr(" size: %1").arg(formatSize(self.dev().size()))
            toolTip += sizeStr
            statusTip += sizeStr
        elif self.dev().isScsi():
            statusTip += " " + self.dev().model()
            curtime = int(time.time())
            ts = self.dev().timeStamp()
            dist = curtime - ts
            if dist > 0:
                toolTip += tr(" (added %1 ago)").arg(formatTimeDistance(dist))
        # finally set the extended info
        self.setToolTip(0, toolTip)
        self.setStatusTip(0, statusTip)
        self.setData(0, Qt.UserRole,
                     QVariant(self.dev().inUse())) # for the delegate
        if self.dev().isScsi():
            self.addBlockDevice(self.dev().blk())

    def overallChildCount(self):
        """Returns the recursive child count."""
        return self._overallChildCount

    def visibleChildCount(self):
        """Returns the recursive child count."""
        return self._visibleChildCount

    def expandAll(self):
        self.setExpanded(True)
        for i in range(0, self.childCount()):
            self.child(i).setExpanded(True)
            self.child(i).expandAll()

class MyTreeWidget(QTreeWidget):
    _visibleRowCount = None # overall count of rows
    _ioThread = None
    _checkInterval = 500 # in milliseconds

    def __init__(self, parent=None):
        QTreeWidget.__init__(self, parent)
        self._ioThread = IoThread(self)
        self._timer = QTimer()
        # connect some signals/slots
        QObject.connect(self,
                        SIGNAL("customContextMenuRequested(const QPoint&)"),
                        self.contextMenu)
        QObject.connect(self,
                        SIGNAL("itemCollapsed(QTreeWidgetItem *)"),
                        self.itemCollapsedOrExpanded)
        QObject.connect(self,
                        SIGNAL("itemExpanded(QTreeWidgetItem *)"),
                        self.itemCollapsedOrExpanded)
        QObject.connect(self._ioThread,
                        SIGNAL("started(void)"),
                        self.connectIoThread)
        self._visibleRowCount = 0
        self._ioThread.start()

    def cleanup(self):
        """Stops the ioThread."""
        self._ioThread.quit()
        while (self._ioThread.isRunning() and
               not self._ioThread.isFinished()):
            self._ioThread.wait()

    def connectIoThread(self):
        if self._ioThread.isRunning():
            QObject.connect(self._ioThread.actionHandler,
                            SIGNAL("actionDone(void)"),
                            self.refreshAction, Qt.QueuedConnection)
            QObject.connect(self._ioThread.actionHandler,
                            SIGNAL("exception(QString, PyQt_PyObject)"),
                            self.exceptionHandler, Qt.QueuedConnection)
            QObject.connect(self._ioThread.actionHandler,
                            SIGNAL("passwordDialog(PyQt_PyObject)"),
                            self.passwordDialog, Qt.BlockingQueuedConnection)
            QObject.connect(self._timer, SIGNAL("timeout(void)"),
                            self.refreshActionIfNeeded)
            self._timer.start(self._checkInterval)

    def passwordDialog(self, resList):
        intext, ok = QInputDialog.getText(self,
                tr("[sudo] Your password"),
                tr("Please enter your password to gain the required \n"+
                   "permissions to perform the selected action:"),
                    QLineEdit.Password)
        resList[0] = intext
        if not ok:
            resList[0] = ""

    def sizeHint(self):
        """Show all entries so that no scrollbar is required"""
        # sum up all column widths
        widthHint = self.sizeHintForColumn(0) + 5 # arbitrary margin
        # consider the header width
        if widthHint < self.header().sizeHint().width():
            widthHint = self.header().sizeHint().width() + 2*2
        # consider the scrollbar width
        widthHint += self.verticalScrollBar().width()
        # update the current/original size hint
        hint = QTreeWidget.sizeHint(self)
        hint.setWidth(widthHint)
        # set height according to # rows
        h = self.indexRowSizeHint(
                self.indexFromItem(
                    self.invisibleRootItem().child(0))) # one row
        heightHint = ((self._visibleRowCount+1) * h 
                      + self.header().height() 
                      + 2 * 2) # magic margin 2+2
        # stay within desktop area
        desktop = QCoreApplication.instance().desktop()
        maxHeight = desktop.availableGeometry(
                        desktop.screenNumber(self)).height()
        if heightHint > maxHeight:
            heightHint = maxHeight
        hint.setHeight(heightHint)
        return hint

    def contextMenu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        if item.dev().isScsi():
            removeAction = MyAction(item.dev().remove,
                                    tr("umount all && remove"), menu)
            if self._ioThread.isRunning():
                QObject.connect(removeAction,
                                SIGNAL("triggered(QString, PyQt_PyObject)"),
                                self._ioThread.actionHandler.doAction,
                                Qt.QueuedConnection)
            menu.addAction(removeAction)
        if item.dev().inUse():
            umountAction = MyAction(item.dev().umount, tr("umount"), menu)
            if self._ioThread.isRunning():
                QObject.connect(umountAction,
                                SIGNAL("triggered(QString, PyQt_PyObject)"),
                                self._ioThread.actionHandler.doAction,
                                Qt.QueuedConnection)
            menu.addAction(umountAction)
        else: # not in use
            mountAction = MyAction(item.dev().mount,
                                   tr("mount with truecrypt"), menu)
            if self._ioThread.isRunning():
                QObject.connect(mountAction,
                                SIGNAL("triggered(QString, PyQt_PyObject)"),
                                self._ioThread.actionHandler.doAction,
                                Qt.QueuedConnection)
            menu.addAction(mountAction)
        menu.addSeparator()
        refreshAction = QAction(tr("refresh all"), menu)
        QObject.connect(refreshAction, SIGNAL("triggered(bool)"),
                        self.refreshAction)
        menu.addAction(refreshAction)
        # fix popup menu position
        pos = self.mapToGlobal(pos)
        pos.setY(pos.y() + self.header().sizeHint().height())
        menu.popup(pos)

    def exceptionHandler(self, text = "", e = None):
        if not e:
            return
        print traceback.format_exc()
        failureText = QString("Action '%1' failed: \n").arg(text)
        try:
            raise e
        except backend.DeviceInUseWarning, dummy:
            QMessageBox.warning(self, tr("Device in Use"), 
                                failureText+
                                tr("The selected device is already in use."),
                                QMessageBox.Ok, QMessageBox.Ok)
        except backend.DeviceHasPartitionsWarning, w:
            QMessageBox.warning(self, tr("Device contains Partitions"),
                                failureText+
                                tr("The selected device contains "+
                                   "several partitions.\n")+
                                tr("Please select one directly."),
                                QMessageBox.Ok, QMessageBox.Ok)
        except backend.RemovalSuccessInfo, e:
            QMessageBox.information(self, tr("Success"), 
                    tr("It is safe to unplug the device now."),
                    QMessageBox.Ok, QMessageBox.Ok)
        except Exception, e:
            QMessageBox.critical(self, tr("An Error Occurred: {0}"
                                          .format(type(e).__name__)),
                                failureText+
                                str(e), 
                                QMessageBox.Ok, QMessageBox.Ok)

    def refreshActionIfNeeded(self, checked = False):
        if backend.STATUS.devStatusChanged() \
        or backend.STATUS.mountStatusChanged():
            # wait a moment after change detected 
            # (let the system create device files, etc..)
            # sometimes, an exception occurs here (for 500ms delay):
            # "Could not find IO device path" BlockDevice.__init__()
            QTimer.singleShot(int(2*self._checkInterval), self.refreshAction)

    def refreshAction(self, checked = False):
        """Updates items as needed"""
# add recursive __eq__/__ne__ to Scsi/BlockDevice
# get status, compare new devices with those in the tree
# if name is the same, remove and add new one at same position
# otherwise remove obsolete items, add new ones on top
# (ignore time -> bus reset)
#        print "refreshAction"
#        rootItem = self.invisibleRootItem()
#        for i in range(0, rootItem.childCount()):
#            print rootItem.child(i).text(0)
        self.clear()

    def reset(self):
        """Deletes all items and rebuild the tree"""
        QTreeWidget.reset(self)
        rootItem = self.invisibleRootItem()
        try:
            for dev in backend.STATUS.getDevices():
#                print "dev:", dev.scsiStr()
                item = MyTreeWidgetItem(dev)
                rootItem.addChild(item)
                item.expandAll()
        except Exception, e:
            self.exceptionHandler(tr("refresh"), e)
        self.setVisibleRowCount()
        QObject.emit(self, SIGNAL("contentChanged(void)"))

    def itemCollapsedOrExpanded(self, item):
        if item.isExpanded():
            item.expanded()
        else: # collapsed
            item.collapsed()
        self.setVisibleRowCount()
        QObject.emit(self, SIGNAL("contentChanged(void)"))

    def setVisibleRowCount(self):
        rootItem = self.invisibleRootItem()
        self._visibleRowCount = rootItem.childCount()
        for i in range(0, rootItem.childCount()):
            self._visibleRowCount += rootItem.child(i).visibleChildCount()

# vim: set ts=4 sw=4 tw=0:
