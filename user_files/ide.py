import sys, os, json, re, subprocess, tempfile, importlib.util
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QToolBar, QAction, QSplitter, QTreeView, QFileSystemModel,
    QTabWidget, QLabel, QLineEdit, QPushButton, QWidget, QTextEdit, QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QListWidget, QInputDialog, QMessageBox, QDockWidget, QShortcut, QCompleter, QMenu
)
from PyQt5.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QIcon, QKeySequence, QTextCursor
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve

APP_CONFIG = os.path.join(os.getcwd(), 'data', 'mini_ide_config_improved.json')
THEMES = {
    # editor/background color plus UI secondary color and an accent for the
    # sidebar/file tree to mimic VSCode-style theme switching.
    'Light': {
        'background': '#ffffff',
        'secondary': '#f0f0f0',
        'foreground': '#222222',
        'keyword': "#adc7c0",
        'string': '#008000',
        'comment': '#888888',
        'accent': "#d1b4a9"
    },
    'Dark': {
        'background': '#23272e',
        'secondary': '#1e1e1e',
        'foreground': '#e6e6e6',
        'keyword': "#0B0B0C",
        'string': '#98C379',
        'comment': '#6A9955',
        'accent': "#060708"
    },
    'Monokai': {
        'background': '#272822',
        'secondary': '#3e3d32',
        'foreground': '#f8f8f2',
        'keyword': "#20181b",
        'string': '#e6db74',
        'comment': '#75715e',
        'accent': "#2b292a"
    },
}
DEFAULT_THEME = 'Dark'
PY_KEYWORDS = [
    'def', 'class', 'if', 'else', 'elif', 'for', 'while', 'import', 'from', 'as', 'return', 'try', 'except', 'with', 'pass',
    'break', 'continue', 'in', 'is', 'not', 'and', 'or', 'lambda', 'yield', 'global', 'nonlocal', 'assert', 'del', 'raise',
    'finally', 'True', 'False', 'None'
]
# very small set for C/CPP/Java/JS
C_KEYWORDS = ['int','float','double','char','long','short','for','while','if','else','return','void','static','struct']

EXT_LANG_MAP = {
    '.py': 'python', '.java': 'java', '.js': 'javascript', '.ts': 'typescript',
    '.cpp': 'cpp', '.c': 'c', '.go': 'go', '.rs': 'rust', '.php': 'php', '.kt': 'kotlin'
}

# ---------- helpers ---------------------------------------------------------

def _get_config_value(key, default=None):
    if os.path.exists(APP_CONFIG):
        try:
            with open(APP_CONFIG, 'r', encoding='utf8') as f:
                cfg = json.load(f)
            return cfg.get(key, default)
        except Exception:
            pass
    return default

def _set_config_value(key, value):
    cfg = {}
    if os.path.exists(APP_CONFIG):
        try:
            with open(APP_CONFIG, 'r', encoding='utf8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg[key] = value
    try:
        os.makedirs(os.path.dirname(APP_CONFIG), exist_ok=True)
        with open(APP_CONFIG, 'w', encoding='utf8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ---------- syntax highlighting ------------------------------------------------

class SyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent, theme, lang='python'):
        super().__init__(parent)
        self.theme = theme
        self.lang = lang
        self._setup_rules()

    def _setup_rules(self):
        self.highlighting_rules = []
        keyword_format = QTextCharFormat(); keyword_format.setForeground(QColor(self.theme['keyword'])); keyword_format.setFontWeight(QFont.Bold)
        keywords = []
        if self.lang == 'python':
            keywords = PY_KEYWORDS
            comment_pattern = r'#.*'
            string_patterns = [r'(".*?"|.*?)', r"'.*?'"]
        else:
            # simple C-like rules
            keywords = C_KEYWORDS
            comment_pattern = r'//.*|/\*.*?\*/'
            string_patterns = [r'".*?"', r"'.*?'"]
        for word in keywords:
            pattern = r'\b' + re.escape(word) + r'\b'
            self.highlighting_rules.append((re.compile(pattern), keyword_format))
        string_format = QTextCharFormat(); string_format.setForeground(QColor(self.theme['string']))
        for pat in string_patterns:
            self.highlighting_rules.append((re.compile(pat), string_format))
        comment_format = QTextCharFormat(); comment_format.setForeground(QColor(self.theme['comment']))
        self.highlighting_rules.append((re.compile(comment_pattern), comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

# ---------- editor widget ----------------------------------------------------

class Editor(QPlainTextEdit):
    def __init__(self, file_path=None, content='', lang='python', theme=THEMES[DEFAULT_THEME], parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.lang = lang
        self.theme = theme
        self.setPlainText(content)
        self.setFont(QFont('Consolas', 12))
        self.setStyleSheet(f'background:{theme["background"]};color:{theme["foreground"]};')
        self.highlighter = SyntaxHighlighter(self.document(), theme, lang)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(['python','cpp','c','javascript','txt'])
        self.lang_combo.setCurrentText(lang)
        self.lang_combo.currentTextChanged.connect(self.set_language)
        self.run_btn = QPushButton('Ishga tushirish / Kompilyatsiya')
        self.run_btn.clicked.connect(self.run_code)
        self.output_box = QTextEdit(); self.output_box.setReadOnly(True)

    def set_language(self, lang):
        self.lang = lang
        self.highlighter.lang = lang
        self.highlighter._setup_rules()

    def run_code(self):
        code = self.toPlainText()
        lang = self.lang_combo.currentText()
        self.output_box.clear()
        try:
            if lang == 'python':
                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.py', encoding='utf8') as f:
                    f.write(code); fname = f.name
                proc = subprocess.run([sys.executable, fname], capture_output=True, text=True)
                self.output_box.setPlainText(proc.stdout + ("\n" + proc.stderr if proc.stderr else ''))
            elif lang in ('cpp','c'):
                ext = '.cpp' if lang == 'cpp' else '.c'
                with tempfile.NamedTemporaryFile('w', delete=False, suffix=ext, encoding='utf8') as f:
                    f.write(code); src = f.name
                exe = src + '.exe'
                compile_res = subprocess.run(['g++', src, '-o', exe], capture_output=True, text=True)
                if compile_res.returncode != 0:
                    self.output_box.setPlainText('Kompilyatsiya xatosi:\n' + compile_res.stderr)
                else:
                    run_res = subprocess.run([exe], capture_output=True, text=True)
                    self.output_box.setPlainText(run_res.stdout + ("\n" + run_res.stderr if run_res.stderr else ''))
            elif lang == 'javascript':
                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.js', encoding='utf8') as f:
                    f.write(code); fname = f.name
                proc = subprocess.run(['node', fname], capture_output=True, text=True)
                self.output_box.setPlainText(proc.stdout + ("\n" + proc.stderr if proc.stderr else ''))
            else:
                self.output_box.setPlainText('Bu til uchun kompilyatsiya/ishga tushirish yo‘q yetkazilmagan yetkazilgan.')
        except Exception as e:
            self.output_box.setPlainText(f'Xatolik: {e}')

# ---------- AI manager ------------------------------------------------------

class AiManager:
    def __init__(self, parent=None):
        self.parent = parent

    def ready(self):
        try:
            import requests
        except ImportError:
            return False
        key = getattr(self.parent, 'openai_key', '')
        return bool(key)

    def ensure_ready(self):
        import requests
        if not self.ready():
            QMessageBox.information(self.parent, "AI sozlanmagan", "Iltimos Settings orqali OpenAI kalitini kiriting va 'requests' paketini o'rnating.")
            return False
        return True

    def query(self, prompt):
        if not self.ensure_ready():
            return "(AI tayyor emas)"
        import requests
        key = self.parent.openai_key
        try:
            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model":"gpt-4o-mini","messages":[{"role":"user","content":prompt}], "max_tokens":600}
            )
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content']
            return f"AI xato: {res.status_code}"
        except Exception as e:
            return f"AI so‘rovida xato: {e}"

# ---------- plugin manager --------------------------------------------------

class PluginManager:
    def __init__(self, ide):
        self.ide = ide
        self.plugins = []

    def load_plugins(self):
        folders = ['plugins']
        if getattr(self.ide, 'is_admin', False):
            folders.append('admin_plugins')
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            for name in os.listdir(folder):
                if name.endswith('.py'):
                    path = os.path.join(folder, name)
                    try:
                        spec = importlib.util.spec_from_file_location(name[:-3], path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, 'register'):
                            module.register(self.ide)
                        self.plugins.append(module)
                    except Exception as e:
                        print('plugin error', name, e)

# ---------- library manager -------------------------------------------------

class LibraryManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Kutubxonalar boshqaruvi')
        v = QVBoxLayout()
        self.list_widget = QListWidget()
        v.addWidget(self.list_widget)
        h = QHBoxLayout()
        install_btn = QPushButton('Yangi o‘rnatish')
        install_btn.clicked.connect(self.add_package)
        uninstall_btn = QPushButton('O‘chirish')
        uninstall_btn.clicked.connect(self.remove_package)
        h.addWidget(install_btn); h.addWidget(uninstall_btn)
        v.addLayout(h)
        self.setLayout(v)
        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        try:
            import pkg_resources # type: ignore
            for d in pkg_resources.working_set:
                self.list_widget.addItem(f"{d.project_name}=={d.version}")
        except Exception:
            pass

    def add_package(self):
        name, ok = QInputDialog.getText(self, 'O‘rnatish', 'Paket nomi:')
        if ok and name:
            subprocess.run([sys.executable, '-m', 'pip', 'install', name])
            self.refresh()

    def remove_package(self):
        name, ok = QInputDialog.getText(self, 'O‘chirish', 'Paket nomi:')
        if ok and name:
            subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', name])
            self.refresh()

# ---------- helper widgets --------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent=None, lang='uz', theme=DEFAULT_THEME, font_size=12, ai_enabled=True):
        super().__init__(parent)
        self.setWindowTitle("Sozlamalar")
        v = QVBoxLayout()
        v.addWidget(QLabel("Tilni tanlash:"))
        self.lang_combo = QComboBox(); self.lang_combo.addItems(['uz','ru','en']); self.lang_combo.setCurrentText(lang)
        v.addWidget(self.lang_combo)
        v.addWidget(QLabel("Mavzuni tanlash:"))
        self.theme_combo = QComboBox(); self.theme_combo.addItems(list(THEMES.keys())); self.theme_combo.setCurrentText(theme)
        v.addWidget(self.theme_combo)
        v.addWidget(QLabel("Shrift o'lchami:"))
        self.font_size = QLineEdit(str(font_size)); v.addWidget(self.font_size)
        self.ai_checkbox = QPushButton("AI yordam yoqilgan" if ai_enabled else "AI yordam o'chirilgan")
        self.ai_checkbox.setCheckable(True); self.ai_checkbox.setChecked(ai_enabled);
        self.ai_checkbox.clicked.connect(self._toggle_ai); v.addWidget(self.ai_checkbox)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self.setLayout(v); self.setFixedWidth(350); self.setFixedHeight(300)

    def _toggle_ai(self):
        checked = self.ai_checkbox.isChecked()
        self.ai_checkbox.setText("AI yordam yoqilgan" if checked else "AI yordam o'chirilgan")

    def get_settings(self):
        return {'lang': self.lang_combo.currentText(),
                'theme': self.theme_combo.currentText(),
                'font_size': int(self.font_size.text()),
                'ai_enabled': self.ai_checkbox.isChecked()}

class HelpPanel(QDockWidget):
    def __init__(self, parent=None, lang='uz'):
        super().__init__("Qo‘llanma / Help / Справка", parent)
        self.text = QTextEdit(); self.text.setReadOnly(True)
        self.setWidget(self.text); self.setMinimumWidth(400)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.update_help(lang)

    def update_help(self, lang):
        doc_path = os.path.join(os.getcwd(), 'docs', f'README_{lang}.md')
        if not os.path.exists(doc_path):
            doc_path = os.path.join(os.getcwd(), 'docs', 'README_uz.md')
        try:
            with open(doc_path, 'r', encoding='utf8') as f:
                self.text.setPlainText(f.read())
        except Exception:
            self.text.setPlainText("Qo‘llanma topilmadi.")

# ---------- main IDE --------------------------------------------------------

class IDE(QMainWindow):
    def __init__(self, is_admin=False):
        super().__init__()
        self.is_admin = is_admin
        self.lang = _get_config_value('lang','uz')
        theme_key = _get_config_value('theme', DEFAULT_THEME)
        self.theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.font_size = _get_config_value('font_size', 12)
        # folder to show in tree; remember between runs
        self.last_folder = _get_config_value('folder', os.getcwd())
        self.openai_key = _get_config_value('openai_key', '')

        self.plugin_manager = PluginManager(self)
        self.ai_manager = AiManager(self)
        # start with side panel hidden; only reveal after user opens a folder or
        # presses the logo/button.  ignore stored preference on startup.
        self.side_panel_visible = False

        self._setup_ui()
        self.plugin_manager.load_plugins()
        # apply theme immediately
        self._apply_theme_to_ui()
        self.statusBar().showMessage('Ready')

    def _setup_ui(self):
        self.setWindowTitle("Editor")
        self.resize(1200,800)
        # activity bar (always visible) with logo and action buttons
        activity_bar = QWidget(); activity_bar.setFixedWidth(50)
        ab_layout = QVBoxLayout(); ab_layout.setContentsMargins(2,2,2,2)
        ab_layout.setSpacing(4)
        # logo / home button
        self.logo = QPushButton("A")
        self.logo.setFlat(True)
        self.logo.setFixedSize(36,36)
        self.logo.setStyleSheet("font-size:18px; font-weight:bold;")
        self.logo.clicked.connect(self.toggle_sidebar)
        self.logo.setCursor(Qt.PointingHandCursor)
        ab_layout.addWidget(self.logo, 0, Qt.AlignHCenter)
        # helper to create icon buttons
        def make_btn(text, callback):
            btn = QPushButton(text)
            btn.setFlat(True)
            btn.setFixedSize(36,36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(callback)
            return btn
        self.btn_libs = make_btn("📦", self._show_lib_panel)
        self.btn_ai = make_btn("🤖", lambda: self._show_ai_console())
        self.btn_build = make_btn("🔨", lambda: self._run_build())
        for b in (self.btn_libs, self.btn_ai, self.btn_build):
            b.setVisible(False)
            ab_layout.addWidget(b, 0, Qt.AlignHCenter)
        ab_layout.addStretch(); activity_bar.setLayout(ab_layout)
        self.activity_bar = activity_bar

        # create terminal widgets early so pages can reference them
        self.terminal = QListWidget()
        self.terminal.setVisible(False)  # hide until there is output
        self.terminal_input = QLineEdit(); self.terminal_input.returnPressed.connect(self.run_command)

        # side_panel_stack will hold multiple pages (file browser, libs, AI, build)
        self.side_panel_stack = QTabWidget()  # use a tab widget as stack; hide tabs
        self.side_panel_stack.tabBar().setVisible(False)
        # page 0: file explorer + terminal
        tree_term_page = QWidget()
        sp_layout = QVBoxLayout(); sp_layout.setContentsMargins(0,0,0,0)
        self.tree = QTreeView(); self.fsmodel = QFileSystemModel()
        self.fsmodel.setRootPath(self.last_folder)
        self.tree.setModel(self.fsmodel)
        self.tree.setRootIndex(self.fsmodel.index(self.last_folder))
        for col in range(1, self.fsmodel.columnCount()):
            self.tree.setColumnHidden(col, True)
        self.tree.clicked.connect(self.on_tree_clicked)
        try:
            accent = self.theme.get('accent') or self.theme.get('background')
            self.tree.setStyleSheet(self.tree.styleSheet() +
                f"QTreeView::item:selected {{ background:{accent}; }}")
        except Exception:
            pass
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        sp_layout.addWidget(self.tree)
        term_widget = QWidget(); tbox = QVBoxLayout(); tbox.addWidget(self.terminal); tbox.addWidget(self.terminal_input)
        term_widget.setLayout(tbox); sp_layout.addWidget(term_widget)
        tree_term_page.setLayout(sp_layout)
        self.side_panel_stack.addTab(tree_term_page, "Files")
        # page 1: libraries panel (reuse LibraryManager widget class but embed)
        lib_page = QWidget(); lib_layout = QVBoxLayout()
        self.lib_panel = LibraryManager(self)  # QDialog subclass but behaves like widget
        lib_layout.addWidget(self.lib_panel)
        lib_page.setLayout(lib_layout)
        self.side_panel_stack.addTab(lib_page, "Libs")
        # page 2: AI panel
        ai_page = QWidget(); ai_layout = QVBoxLayout()
        self.ai_input = QTextEdit(); self.ai_input.setPlaceholderText('Savolingiz...')
        ai_send = QPushButton('Yubor'); ai_send.clicked.connect(self._ai_send)
        self.ai_output = QTextEdit(); self.ai_output.setReadOnly(True)
        ai_layout.addWidget(self.ai_input); ai_layout.addWidget(ai_send); ai_layout.addWidget(self.ai_output)
        ai_page.setLayout(ai_layout); self.side_panel_stack.addTab(ai_page, "AI")
        # page 3: build output
        build_page = QWidget(); build_layout = QVBoxLayout()
        self.build_output = QTextEdit(); self.build_output.setReadOnly(True)
        build_layout.addWidget(self.build_output)
        build_page.setLayout(build_layout); self.side_panel_stack.addTab(build_page, "Build")
        # wrap stack in container to allow hide/show
        side_panel = QWidget(); panel_layout = QVBoxLayout(); panel_layout.setContentsMargins(0,0,0,0); panel_layout.addWidget(self.side_panel_stack); side_panel.setLayout(panel_layout)
        self.side_panel = side_panel

        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.terminal = QListWidget()
        self.terminal.setVisible(False)  # hide until there is output
        self.terminal_input = QLineEdit(); self.terminal_input.returnPressed.connect(self.run_command)

        # store sidebar widget for toggling
        # activity_bar used to hold icons; keep reference for restyling
        self.activity_bar = activity_bar
        # replace old left_split with side_panel under control
        main_split = QSplitter(Qt.Horizontal)
        main_split.addWidget(self.activity_bar)
        main_split.addWidget(self.side_panel)
        main_split.addWidget(self.tabs)
        self.main_split = main_split
        self.setCentralWidget(main_split)
        # apply visibility state; start hidden regardless of config
        self.side_panel_visible = False
        if not self.side_panel_visible:
            self.side_panel.setMaximumWidth(0)
            self.side_panel.setVisible(False)
            self.main_split.setSizes([1,0,5])  # keep activity bar visible
        else:
            self.side_panel.setMaximumWidth(200)
            self.side_panel.setVisible(True)
            self.main_split.setSizes([1,3,5])

        tb = QToolBar(); self.addToolBar(tb)
        tb.addAction(self._tr('Yangi'), self.new_file)
        # add shortcut for sidebar toggle
        self.shortcut_toggle = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_toggle.activated.connect(self.toggle_sidebar)
        tb.addAction(self._tr('Ochish'), self.open_file)
        tb.addAction(self._tr('Saqlash'), self.save_file)
        # folder action shown only when a folder has been opened
        self.act_open_folder = tb.addAction('Folder ochish', self.open_folder)
        if not self.last_folder or not os.path.isdir(self.last_folder):
            self.act_open_folder.setVisible(False)
        tb.addAction('Fayl qo‘shish', self.add_file)
        tb.addAction('Papka qo‘shish', self.add_folder)
        tb.addAction('O‘chirish', self.delete_selected)
        tb.addAction('Nomini o‘zgartirish', self.rename_selected)
        tb.addAction('Qidiruv', self.open_search)
        tb.addAction(self._tr('Sozlamalar'), self.open_settings)
        tb.addAction('Toggle sidebar', self.toggle_sidebar)
        # add explicit button to toggle terminal visibility
        tb.addAction('Toggle terminal', self.toggle_terminal)
        if self.is_admin:
            tb.addAction('Kutubxonalar', self.open_library_manager)
            tb.addAction('GitHub’dan yuklash', self.github_download)
            tb.addAction('Admin sozlamalar', self.open_admin_settings)
        tb.addAction('Help', lambda: HelpPanel(self, self.lang).show())
        self.toolbar = tb

        # open welcome tab
        self.new_file(welcome=True)
        # set window icon if available
        icon_path = os.path.join(os.getcwd(), 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
            except Exception as e:
                print('icon load failed', e)

    # utility methods
    def _tr(self, text):
        uz = {'Yangi':'Yangi','Ochish':'Fayl ochish','Saqlash':'Saqlash','Sozlamalar':'Sozlamalar','Tayyor':'Tayyor','Xush kelibsiz':'Xush kelibsiz'}
        en = {'Yangi':'New','Ochish':'Open','Saqlash':'Save','Sozlamalar':'Settings','Tayyor':'Ready','Xush kelibsiz':'Welcome'}
        return uz.get(text,text) if self.lang=='uz' else en.get(text,text)

    def _apply_theme_to_ui(self):
        # apply stylesheet to main window and set default fg/bg on root
        # use explicit secondary color if provided, otherwise fall back to
        # the standard background value so that existing themes continue to
        # work.  Many widget types are styled here so that changing the theme
        # affects the entire interface, not just editors and dialogs.
        sec = self.theme.get('secondary', self.theme.get('background', ''))
        bg = self.theme.get('background', sec)
        fg = self.theme.get('foreground', '#000')
        # build a comprehensive stylesheet; order matters because later rules
        # override earlier ones if they overlap.  the intent is to make the
        # *editor content* use `background` while the rest of the UI uses
        # `secondary` so that panels/toolbars/menus are distinct like in VSCode.
        style = f"""
QMainWindow {{ background:{sec}; color:{fg}; }}
QToolBar, QMenuBar, QMenu, QTabBar, QTabWidget, QDockWidget {{ background:{sec}; color:{fg}; }}
QWidget {{ background:{sec}; color:{fg}; }}
QLabel, QMenu, QToolButton, QPushButton {{ color:{fg}; }}
QLineEdit, QComboBox, QListWidget, QTreeView, QTableView, QSpinBox, QTextEdit, QPlainTextEdit {{
    background:{bg}; color:{fg}; }}
QPlainTextEdit {{ background:{bg}; color:{fg}; }}
"""
        try:
            self.setStyleSheet(style)
        except Exception:
            pass
        # update toolbar button texts if language changed
        for action in self.toolbar.actions():
            txt = action.text()
            if txt in ['Yangi','New','Ochish','Open','Saqlash','Save','Sozlamalar','Settings','Help']:
                action.setText(self._tr(txt))
        # reapply sidebar style as colours may rely on theme
        self._apply_sidebar_style()
        # propagate colours to any dialog-like widgets created by the global app
        try:
            app = QApplication.instance()
            if app:
                app.setStyleSheet(f"QMessageBox, QFileDialog, QInputDialog {{ background:{sec}; color:{fg}; }}")
        except Exception:
            pass
        # update all open editors with new theme
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w is None:
                continue
            ed = w.findChild(Editor)
            if ed:
                ed.theme = self.theme
                ed.setStyleSheet(f'background:{self.theme.get("background","")};color:{self.theme.get("foreground",
                    "")}')
                try:
                    ed.highlighter.theme = self.theme
                    ed.highlighter._setup_rules()
                except Exception:
                    pass
        # style tab widget area
        try:
            tab_bg = self.theme.get('secondary', '')
            tab_fg = self.theme.get('foreground', '')
            self.tabs.setStyleSheet(f'QTabWidget {{background:{tab_bg}; color:{tab_fg};}}')
        except Exception:
            pass
        # optionally style terminal widget
        try:
            term_bg = self.theme.get('background', '')
            term_fg = self.theme.get('foreground', '')
            self.terminal.setStyleSheet(f'background:{term_bg};color:{term_fg};')
        except Exception:
            pass

    def _lang(self,path):
        return EXT_LANG_MAP.get(os.path.splitext(path)[1].lower(),'python')

    # file operations (new, open, save) similar to previous code
    def new_file(self, welcome=False):
        ed = Editor(theme=self.theme)
        w = QWidget(); vbox=QVBoxLayout(); hbox=QHBoxLayout(); hbox.addWidget(ed.lang_combo); hbox.addWidget(ed.run_btn)
        vbox.addLayout(hbox); vbox.addWidget(ed); vbox.addWidget(QLabel('Natija:')); vbox.addWidget(ed.output_box)
        w.setLayout(vbox);
        title = self._tr('Xush kelibsiz') if welcome else self._tr('Yangi')
        self.tabs.addTab(w, title); self.tabs.setCurrentWidget(w)

    def open_file(self):
        path,_ = QFileDialog.getOpenFileName(self,self._tr('Ochish'), self.last_folder,'All Files (*)')
        if not path: return
        self._open_file_path(path)

    def _open_file_path(self, path):
        # helper to load a file given an absolute path
        # remember folder
        self.last_folder = os.path.dirname(path)
        _set_config_value('folder', self.last_folder)
        try:
            with open(path,'r',encoding='utf8') as f: content=f.read()
            lang=self._lang(path)
            ed = Editor(file_path=path, content=content, lang=lang, theme=self.theme)
            w=QWidget(); vbox=QVBoxLayout(); hbox=QHBoxLayout(); hbox.addWidget(ed.lang_combo); hbox.addWidget(ed.run_btn)
            vbox.addLayout(hbox); vbox.addWidget(ed); vbox.addWidget(QLabel('Natija:')); vbox.addWidget(ed.output_box)
            w.setLayout(vbox)
            self.tabs.addTab(w, os.path.basename(path)); self.tabs.setCurrentWidget(w)
        except Exception:
            pass

    def save_file(self):
        w = self.tabs.currentWidget()
        if not w: return
        ed = w.findChild(Editor)
        if not ed: return
        path = ed.file_path
        if not path:
            path,_ = QFileDialog.getSaveFileName(self,self._tr('Saqlash'), self.last_folder,'All Files (*)')
            if not path: return
            ed.file_path = path
        # remember folder after saving
        self.last_folder = os.path.dirname(path)
        _set_config_value('folder', self.last_folder)
        try:
            with open(path,'w',encoding='utf8') as f: f.write(ed.toPlainText())
        except Exception:
            pass

    def add_file(self):
        idx = self.tree.currentIndex();
        dir_path = self.fsmodel.filePath(idx) if self.fsmodel.isDir(idx) else os.path.dirname(self.fsmodel.filePath(idx))
        name,ok = QInputDialog.getText(self,'Fayl qo‘shish','Fayl nomi:')
        if ok and name:
            try:
                with open(os.path.join(dir_path,name),'w',encoding='utf8'):
                    pass
            except Exception:
                pass

    def add_folder(self):
        idx = self.tree.currentIndex();
        dir_path = self.fsmodel.filePath(idx) if self.fsmodel.isDir(idx) else os.path.dirname(self.fsmodel.filePath(idx))
        name,ok = QInputDialog.getText(self,'Papka qo‘shish','Papka nomi:')
        if ok and name:
            try:
                os.makedirs(os.path.join(dir_path,name), exist_ok=True)
            except Exception:
                pass

    def delete_selected(self):
        idx = self.tree.currentIndex(); path = self.fsmodel.filePath(idx)
        if not path: return
        confirm = QMessageBox.question(self,'O‘chirish',f'{path}ni o‘chirilsinmi?',QMessageBox.Yes|QMessageBox.No)
        if confirm==QMessageBox.Yes:
            try:
                if os.path.isdir(path): import shutil; shutil.rmtree(path)
                else: os.remove(path)
            except Exception:
                pass

    def rename_selected(self):
        idx=self.tree.currentIndex(); path=self.fsmodel.filePath(idx)
        if not path: return
        new,ok=QInputDialog.getText(self,'Nomini o‘zgartirish','Yangi nom:')
        if ok and new:
            try: os.rename(path, os.path.join(os.path.dirname(path),new))
            except Exception:
                pass

    def open_search(self):
        text,ok=QInputDialog.getText(self,'Qidiruv','Qidiriladigan matn:')
        if not ok or not text: return
        results=[]
        for root,dirs,files in os.walk(self.last_folder):
            for fn in files:
                p=os.path.join(root,fn)
                try:
                    with open(p,'r',encoding='utf8') as f:
                        for i,line in enumerate(f,1):
                            if text in line: results.append(f'{p} ({i}): {line.strip()}')
                except Exception:
                    continue
        QMessageBox.information(self,'Qidiruv natijasi','\n'.join(results) if results else 'Hech narsa topilmadi.')

    def open_settings(self):
        theme_key = [k for k,v in THEMES.items() if v == self.theme][0]
        dlg = SettingsDialog(self, self.lang, theme_key, self.font_size, _get_config_value('ai_enabled',True))
        if dlg.exec_()==QDialog.Accepted:
            s=dlg.get_settings()
            self.lang=s['lang']; _set_config_value('lang',self.lang)
            _set_config_value('theme',s['theme']);
            self.theme=THEMES[s['theme']]
            self.font_size=s['font_size']; _set_config_value('font_size',self.font_size)
            _set_config_value('ai_enabled', s['ai_enabled'])
            # reapply theme and sidebar style after theme change
            self._apply_theme_to_ui()


    def on_tree_clicked(self,index):
        """Open a file when it's clicked in the sidebar tree."""
        path = self.fsmodel.filePath(index)
        if os.path.isfile(path):
            self._open_file_path(path)

    def close_tab(self,idx):
        self.tabs.removeTab(idx)
        # ensure at least one tab exists to avoid errors elsewhere
        if self.tabs.count() == 0:
            self.new_file(welcome=True)
    def on_tab_changed(self,idx):
        w=self.tabs.widget(idx)
        ed=w.findChild(Editor)
        if ed and ed.file_path:
            self.setWindowTitle(f"Editor - {os.path.basename(ed.file_path)}")

    def run_command(self):
        cmd=self.terminal_input.text()
        if not cmd: return
        # show terminal when executing anything
        if not self.terminal.isVisible():
            self.terminal.setVisible(True)
        try:
            res=subprocess.run(cmd, shell=True, capture_output=True, text=True)
            self.terminal.addItem(f"> {cmd}")
            self.terminal.addItem(res.stdout)
            if res.stderr: self.terminal.addItem(res.stderr)
        except Exception as e:
            self.terminal.addItem(str(e))
        self.terminal_input.clear()
        # hide terminal again if it has no meaningful content
        self.update_terminal_visibility()

    def open_library_manager(self):
        dlg=LibraryManager(self); dlg.exec_()

    def _show_lib_panel(self):
        if not self.side_panel_visible:
            # simply reveal side panel without prompting for folder
            self.side_panel_visible = True
            _set_config_value('sidebar_visible', True)
            self.side_panel.setVisible(True)
            self.side_panel.setMaximumWidth(200)
            self.main_split.setSizes([1,3,5])
        self.side_panel_stack.setCurrentIndex(1)

    def _show_ai_console(self):
        if not self.ai_manager.ensure_ready():
            return
        if not self.side_panel_visible:
            self.side_panel_visible = True
            _set_config_value('sidebar_visible', True)
            self.side_panel.setVisible(True)
            self.side_panel.setMaximumWidth(200)
            self.main_split.setSizes([1,3,5])
        self.side_panel_stack.setCurrentIndex(2)
        # clear previous output
        self.ai_output.clear()

    def _ai_send(self):
        prompt = self.ai_input.toPlainText().strip()
        if not prompt:
            return
        answer = self.ai_manager.query(prompt)
        self.ai_output.append(answer)

    def _run_build(self):
        if not self.side_panel_visible:
            self.side_panel_visible = True
            _set_config_value('sidebar_visible', True)
            self.side_panel.setVisible(True)
            self.side_panel.setMaximumWidth(200)
            self.main_split.setSizes([1,3,5])
        self.side_panel_stack.setCurrentIndex(3)
        try:
            res = subprocess.run([sys.executable, 'build.py'], capture_output=True, text=True)
            self.build_output.setPlainText(res.stdout + ('\n' + res.stderr if res.stderr else ''))
        except Exception as e:
            self.build_output.setPlainText(f'Xato: {e}')

    def toggle_terminal(self):
        # simple show/hide with state tracking
        vis = self.terminal.isVisible()
        self.terminal.setVisible(not vis)
        if not vis and self.terminal.count() == 0:
            # if showing empty terminal, keep hidden until something added
            self.terminal.setVisible(False)

    def update_terminal_visibility(self):
        # ensure terminal visible only when it has at least one item
        if self.terminal.count() == 0:
            self.terminal.setVisible(False)
        else:
            self.terminal.setVisible(True)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Folder ochish', self.last_folder or os.getcwd())
        if folder:
            self.last_folder = folder
            self.fsmodel.setRootPath(folder)
            self.tree.setRootIndex(self.fsmodel.index(folder))
            _set_config_value('folder', folder)
            # show the side panel with folder contents
            if not self.side_panel_visible:
                self.side_panel_visible = True
                _set_config_value('sidebar_visible', True)
                self.side_panel.setVisible(True)
                self.side_panel.setMaximumWidth(200)
                self.main_split.setSizes([1,3,5])
                self.side_panel_stack.setCurrentIndex(0)
            if hasattr(self, 'act_open_folder'):
                self.act_open_folder.setVisible(True)

    def _tree_context_menu(self, pos):
        # simple context menu for tree: open folder or copy path
        idx = self.tree.indexAt(pos)
        menu = QMenu(self)
        open_folder_action = menu.addAction('Bu papkani ochish')
        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if action == open_folder_action:
            path = self.fsmodel.filePath(idx)
            if os.path.isdir(path):
                self.last_folder = path
                self.fsmodel.setRootPath(path)
                self.tree.setRootIndex(self.fsmodel.index(path))
                _set_config_value('folder', path)

    def _apply_sidebar_style(self):
        # compute accent purely from the current theme so that switching
        # themes always updates the sidebar colour accordingly.  if the
        # theme provides an explicit `accent` we use it, otherwise fall back
        # to the editor `background` colour (resulting in a unified look for
        # simple themes).
        accent = None
        if isinstance(self.theme, dict):
            accent = self.theme.get('accent')
        if not accent:
            # if theme has no accent, use background; final fallback to blue
            accent = self.theme.get('background', '#0057b7')
        # apply accent to the activity bar and use theme background for panel
        self.activity_bar.setStyleSheet(f"background:{accent};")
        self.side_panel.setStyleSheet(f"background:{self.theme.get('background','#000')};")
        # restyle logo and action buttons to match accent/foreground
        try:
            fg = self.theme.get('foreground','#fff')
            self.logo.setStyleSheet(f"font-size:18px; font-weight:bold; background:{accent}; color:{fg}")
            for b in (self.btn_libs, self.btn_ai, self.btn_build):
                b.setStyleSheet(f"font-size:16px; background:{accent}; color:{fg}")
        except Exception:
            pass
        # also colour the file tree; ensure selection is visible against editor
        try:
            fg = self.theme.get('foreground', '#fff')
            self.tree.setStyleSheet(f"""
                background:{accent};
                color:{fg};
                selection-background-color:{self.theme.get('background','')};
            """)
        except Exception:
            pass

    def toggle_sidebar(self):
        # if folder not selected, open it
        if not self.last_folder or not os.path.isdir(self.last_folder):
            self.open_folder()
            return
        # animate side_panel instead of activity_bar
        target = 200 if not self.side_panel_visible else 0
        anim = QPropertyAnimation(self.side_panel, b"maximumWidth")
        anim.setDuration(200)
        anim.setStartValue(self.side_panel.width())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        self.side_panel_visible = not self.side_panel_visible
        _set_config_value('sidebar_visible', self.side_panel_visible)
        def on_finished():
            if not self.side_panel_visible:
                self.side_panel.setVisible(False)
                self.main_split.setSizes([1,0,5])
            else:
                self.side_panel.setVisible(True)
                self.main_split.setSizes([1,3,5])
        anim.finished.connect(on_finished)
        # toggle action buttons visibility
        for b in (self.btn_libs, self.btn_ai, self.btn_build):
            b.setVisible(self.side_panel_visible)
        # when opening panel normally, switch back to files page
        if self.side_panel_visible:
            self.side_panel_stack.setCurrentIndex(0)

    def open_admin_settings(self):
        # reuse auth module's settings dialog
        try:
            from user_files.auth import AuthSettingsDialog
            dlg = AuthSettingsDialog(self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.warning(self, 'Admin', f'Settings ochilmadi: {e}')

    def github_download(self):
        url,ok = QInputDialog.getText(self,'GitHub','Repo URL:')
        if not ok or not url: return
        dest = QFileDialog.getExistingDirectory(self,'Saqlanish papkasi')
        if not dest: return
        try:
            subprocess.run(['git','clone',url,dest], check=True)
            QMessageBox.information(self,'GitHub','Yuklandi')
        except Exception as e:
            QMessageBox.warning(self,'GitHub',f'Xato: {e}')

# end of file
