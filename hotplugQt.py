"""Qt GUI for the hotplug manager
"""

import sys
from PyQt4 import QtCore, QtGui
from mainwindow import Ui_MainWindow

import hotplugBackend

class MainWindow(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(s, parent=None):
        QtGui.QMainWindow.__init__(s, parent)
        s.setupUi(s)
        #s.treeWidget.setHeaderHidden(True) # qt 4.4
        s.rebuild()

    def rebuild(s):
        s.treeWidget.clear()
        devList, devInfoList = hotplugBackend.status.getDevices()
        rootItem = s.treeWidget.invisibleRootItem()
        for devInfo in devInfoList:
            name = reduce(lambda a, b: a+", "+b, devInfo[0])
            item = QtGui.QTreeWidgetItem([name])
            rootItem.addChild(item)
            print name


def qtMenu(argv):
    app = QtGui.QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
