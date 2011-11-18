# -*- coding: utf-8 -*-
# dfmonQt.py
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

"""Qt GUI for dfmon.
"""

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mainwindow import Ui_MainWindow

def tr(s):
   return QCoreApplication.translate(None, s)

class MyItemDelegate(QItemDelegate):
    """Row color based on device usage state."""
    def __init__(s, parent = None):
        QItemDelegate.__init__(s, parent)

    def paint (s, painter, option, index):
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
        QItemDelegate.paint(s, painter, option, index)

class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(s, parent = None):
        QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        delegate = MyItemDelegate(s.treeWidget.itemDelegate())
        s.treeWidget.setItemDelegate(delegate)
        headerItem = s.treeWidget.headerItem()
        headerItem.setText(0,tr("available devices"))
        headerItem.setTextAlignment(0, Qt.AlignHCenter)
        headerItem.setToolTip(0, QString("%1 %2").arg(s.windowTitle(), "0.1")
                            +QString("\n%1").arg(u"Copyright (C) 2010  Ingo Bressler")
                            +QString("\n%1\n%2\n%3").arg("This program comes with ABSOLUTELY", "NO WARRANTY. This is free software, use", "and redistribute it under the terms of the GPLv3.")
                            +QString("\n%1\n%2").arg(tr("For information, feedback and contributions, please visit:"), "http://github.com/ingob/dfmon"))
        s.treeWidget.setMouseTracking(True)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.updateGeometry)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.centralwidget.updateGeometry)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.contentChanged)
        s.treeWidget.clear() # clears and rebuilds the tree

    def closeEvent(s, event):
        s.treeWidget.cleanup()
        QMainWindow.closeEvent(s, event)

    def keyPressEvent(s, keyEvent):
        QMainWindow.keyPressEvent(s, keyEvent)
        # <esc> closes the window/application
        if keyEvent.key() == Qt.Key_Escape:
            s.close()

    def contentChanged(s):
#        s.treeWidget.adjustSize()
        s.treeWidget.updateGeometry()
#        s.resize(200, 256)
        sh = s.sizeHint()
        s.setFixedWidth(sh.width())

# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
