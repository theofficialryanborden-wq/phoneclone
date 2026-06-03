BLUESTACKS_STYLE = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", sans-serif;
}
QFrame#sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}
QFrame#displayFrame {
    background-color: #010409;
    border: 1px solid #30363d;
    border-radius: 12px;
}
QPushButton[class="nav"] {
    background-color: transparent;
    color: #8b949e;
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}
QPushButton[class="nav"]:hover {
    background-color: #21262d;
    color: #e6edf3;
}
QPushButton[class="nav"]:checked {
    background-color: #1f6feb;
    color: #ffffff;
}
QPushButton[class="primary"] {
    background-color: #238636;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 14px;
}
QPushButton[class="primary"]:hover { background-color: #2ea043; }
QPushButton[class="action"] {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton[class="action"]:hover { background-color: #30363d; }
QLabel#brand {
    font-size: 20px;
    font-weight: 800;
    color: #58a6ff;
}
QLabel#status {
    color: #8b949e;
    font-size: 12px;
}
QProgressBar {
    border: none;
    border-radius: 6px;
    background: #21262d;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: #1f6feb;
}
QListWidget {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item {
    padding: 10px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background: #1f6feb;
}
QFrame#welcomeCard {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 16px;
}
"""
