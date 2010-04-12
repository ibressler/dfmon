"""Qt GUI for the hotplug manager
"""

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mainwindow import Ui_MainWindow

def tr(s):
   return QCoreApplication.translate(None, s)

class MyItemDelegate(QItemDelegate):

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
        headerItem.setToolTip(0,s.windowTitle()
                              +tr("\nFor feedback and contributions, please visit URL."))
        s.treeWidget.setMouseTracking(True)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.updateGeometry)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.centralwidget.updateGeometry)
        QObject.connect(s.treeWidget, SIGNAL("contentChanged(void)"), s.contentChanged)
        s.treeWidget.clear() # clears and rebuilds the tree

    def keyPressEvent(s, keyEvent):
        QMainWindow.keyPressEvent(s, keyEvent)
        if keyEvent.key() == Qt.Key_Escape:
            s.close()
            
    def contentChanged(s):
#        print "contentChanged"
#        print "trr height:", s.treeWidget.size().height()
        sh = s.sizeHint()
        # s.resize(s.treeWidget.sizeHint()) # does not work
        s.setMinimumSize(sh)
        s.setMaximumSize(sh)
#        print "blubb", s.width(), s.height()

# end MainWindow

def qtMenu(argv):
    app = QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
