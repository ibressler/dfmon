# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'mainwindow.ui'
#
# Created: Mon Apr 12 16:53:10 2010
#      by: PyQt4 UI code generator 4.3.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")

        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")

        self.vboxlayout = QtGui.QVBoxLayout(self.centralwidget)
        self.vboxlayout.setObjectName("vboxlayout")

        self.treeWidget = MyTreeWidget(self.centralwidget)

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.treeWidget.sizePolicy().hasHeightForWidth())
        self.treeWidget.setSizePolicy(sizePolicy)
        self.treeWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.treeWidget.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.treeWidget.setObjectName("treeWidget")
        self.vboxlayout.addWidget(self.treeWidget)
        MainWindow.setCentralWidget(self.centralwidget)

        self.menubar = QtGui.QMenuBar(MainWindow)
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)

        self.statusbar = QtGui.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Hotplug Manager", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(0,QtGui.QApplication.translate("MainWindow", "1", None, QtGui.QApplication.UnicodeUTF8))

from mytreewidget import MyTreeWidget
