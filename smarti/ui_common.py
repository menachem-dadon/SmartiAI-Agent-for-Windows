"""Legacy Qt compatibility imports.

Core/runtime code imports :mod:`smarti.common`, which is deliberately free of
Qt.  The transitional PyQt client imports this module to retain the historical
wildcard namespace until its presentation modules are removed at Point 17.
"""

from .common import *

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QBoxLayout,
                             QHBoxLayout, QTextEdit, QPlainTextEdit, QPushButton, QLabel,
                             QScrollArea, QFrame, QMenu, QLineEdit, QTextBrowser, QProgressBar,
                             QCheckBox, QFormLayout, QSizePolicy, QMessageBox, QComboBox, QSystemTrayIcon, QSlider, QStackedWidget, QStyleOptionButton, QStyle, QGraphicsOpacityEffect, QGraphicsEffect, QGraphicsDropShadowEffect, QFileDialog, QDialog, QDialogButtonBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView, QToolTip)
from PyQt6.QtCore import Qt, QEvent, QObject, QThread, pyqtSignal, QSize, QTimer, QPoint, QPropertyAnimation, QEasingCurve, QElapsedTimer, QRectF, QUrl
from PyQt6.QtGui import QIcon, QFont, QFontDatabase, QFontMetrics, QPixmap, QCursor, QColor, QPainter, QPainterPath, QPen, QMovie, QTextOption, QPalette, QTextCursor, QLinearGradient, QBrush, QImage, QDesktopServices, QRegion


__all__ = [name for name in globals() if not name.startswith("__")]
