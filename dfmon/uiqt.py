# -*- coding: utf-8 -*-
# uiqt.py
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

"""Qt GUI for dfmon.
"""

from PyQt4.QtCore import (Qt, QString, QRect, QObject, QCoreApplication,
                          SIGNAL)
from PyQt4.QtGui import (QItemDelegate, QStyle, QColor, QApplication,
                         QMainWindow)
from mainwindow import Ui_MainWindow

def tr(s):
    return QCoreApplication.translate(None, s)

class MyItemDelegate(QItemDelegate):
    """Row color based on device usage state."""
    def __init__(self, parent = None):
        QItemDelegate.__init__(self, parent)

    def paint (self, painter, option, index):
        if not (QStyle.State_Selected & option.state):
            r = QRect(option.rect)
            r.setX(0)
            # test if item/device is in use
            if index.data(Qt.UserRole).toBool():
                painter.setBrush(QColor(255, 0, 0, 32))
            else:
                painter.setBrush(QColor(0, 255, 0, 128))
            painter.setPen(Qt.lightGray)
            painter.drawRect(r)
        QItemDelegate.paint(self, painter, option, index)

class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, parent = None):
        QMainWindow.__init__(self, parent)
        self.setupUi(self)
        #self.treeWidget.setHeaderHidden(True) # qt 4.4
        delegate = MyItemDelegate(self.treeWidget.itemDelegate())
        self.treeWidget.setItemDelegate(delegate)
        headerItem = self.treeWidget.headerItem()
        headerItem.setText(0, tr("available devices"))
        headerItem.setTextAlignment(0, Qt.AlignHCenter)
        headerItem.setToolTip(0,
                              QString("%1 %2")
                              .arg(self.windowTitle(), "0.1")+
                              QString("\n%1")
                              .arg(u"Copyright (C) 2010  Ingo Bressler")+
                              QString("\n%1\n%2\n%3")
                              .arg("This program comes with ABSOLUTELY",
                                   "NO WARRANTY. This is free software, use",
                                   "and redistribute it under the terms of "+
                                   "the GPLv3.")+
                              QString("\n%1\n%2")
                              .arg(tr("For information, feedback and "+
                                      "contributions, please visit:"),
                                   "http://github.com/ibressler/dfmon"))
        self.treeWidget.setMouseTracking(True)
        QObject.connect(self.treeWidget,
                        SIGNAL("contentChanged(void)"),
                        self.updateGeometry)
        QObject.connect(self.treeWidget, 
                        SIGNAL("contentChanged(void)"),
                        self.centralwidget.updateGeometry)
        QObject.connect(self.treeWidget,
                        SIGNAL("contentChanged(void)"),
                        self.contentChanged)
        self.treeWidget.clear() # clears and rebuilds the tree

    def closeEvent(self, event):
        self.treeWidget.cleanup()
        QMainWindow.closeEvent(self, event)

    def keyPressEvent(self, keyEvent):
        QMainWindow.keyPressEvent(self, keyEvent)
        # <esc> closes the window/application
        if keyEvent.key() == Qt.Key_Escape:
            self.close()

    def contentChanged(self):
#        self.treeWidget.adjustSize()
        self.treeWidget.updateGeometry()
#        self.resize(200, 256)
        sh = self.sizeHint()
        self.setFixedWidth(sh.width())

# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()

# vim: set ts=4 sw=4 tw=0:
