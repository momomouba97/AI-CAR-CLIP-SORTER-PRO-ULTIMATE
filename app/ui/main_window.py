from pathlib import Path
import json
import re
import shutil
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QDoubleSpinBox, QComboBox, QCheckBox, QProgressBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QMessageBox, QGroupBox,
    QSplitter, QListWidget, QListWidgetItem, QFormLayout, QSpinBox, QHeaderView
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from app.core.settings import load_settings, save_settings
from app.core.workers import SceneWorker, ExportWorker, UploadWorker

STYLE = """
QWidget { background:#101318; color:#F4F6FA; font-family:Arial; font-size:13px; }
QMainWindow { background:#101318; }
QTabWidget::pane { border:1px solid #2B3441; border-radius:10px; }
QTabBar::tab { background:#171C24; padding:12px 20px; margin:3px; border-radius:7px; }
QTabBar::tab:selected { background:#285DA8; }
QGroupBox { border:1px solid #2B3441; border-radius:10px; margin-top:12px; padding:12px; font-weight:bold; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; }
QPushButton { background:#263241; border:1px solid #354355; border-radius:8px; padding:9px 14px; }
QPushButton:hover { background:#34465D; }
QPushButton:pressed { background:#1D4F91; }
QPushButton#primary { background:#3985F7; border:0; font-weight:bold; }
QPushButton#danger { background:#7D3038; border:0; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QTableWidget, QListWidget {
 background:#171C24; border:1px solid #303B49; border-radius:7px; padding:7px;
}
QHeaderView::section { background:#202936; padding:8px; border:0; }
QProgressBar { background:#202936; border:0; border-radius:6px; height:14px; text-align:center; }
QProgressBar::chunk { background:#3985F7; border-radius:6px; }
QVideoWidget { background:#050608; border:1px solid #303B49; border-radius:8px; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI CAR CLIP SORTER PRO ULTIMATE")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)
        self.settings = load_settings()
        self.scenes = []
        self.exported = []
        self.scene_worker = None
        self.export_worker = None
        self.upload_worker = None
        self.sort_files = []
        self.sort_index = 0
        self.undo_stack = []
        self.skipped = []
        self.video_queue = []
        self.queue_index = 0
        self.batch_running = False
        self.batch_total = 0
        self.batch_done = 0
        self._build_ui()
        self._apply_settings()
        self._refresh_stats()
        self._load_sort_list()

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        header = QHBoxLayout()
        brand = QLabel("AI CAR CLIP SORTER <span style='color:#3985F7'>PRO</span> <span style='color:#9AA7B8'>ULTIMATE</span>")
        brand.setTextFormat(Qt.RichText)
        brand.setStyleSheet("font-size:22px;font-weight:800;padding:8px;")
        self.status_label = QLabel("جاهز للعمل")
        self.status_label.setStyleSheet("color:#9AA7B8;")
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(self.status_label)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.dashboard_tab = QWidget()
        self.splitter_tab = QWidget()
        self.sorter_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.dashboard_tab, "لوحة التحكم")
        self.tabs.addTab(self.splitter_tab, "تقسيم الفيديو")
        self.tabs.addTab(self.sorter_tab, "فرز المقاطع")
        self.tabs.addTab(self.settings_tab, "الإعدادات")
        self._build_dashboard()
        self._build_splitter()
        self._build_sorter()
        self._build_settings()
        self._build_menu()

    def _build_menu(self):
        undo = QAction("تراجع عن آخر تصنيف", self)
        undo.setShortcut(QKeySequence("Ctrl+Z"))
        undo.triggered.connect(self.undo_sort)
        self.addAction(undo)

    def _build_dashboard(self):
        layout = QVBoxLayout(self.dashboard_tab)
        intro = QLabel("مركز إدارة عمليات الفيديو")
        intro.setStyleSheet("font-size:20px;font-weight:700;padding:10px;")
        layout.addWidget(intro)
        grid = QGridLayout()
        self.stat_labels = {}
        for i, (key, title) in enumerate([
            ("scenes", "المشاهد المكتشفة"), ("exported", "المقاطع المصدرة"),
            ("moving", "سيارات متحركة"), ("stopping", "سيارات متوقفة"),
            ("excluded", "مقاطع مستبعدة"), ("uploads", "عمليات الرفع")
        ]):
            box = QGroupBox(title)
            v = QVBoxLayout(box)
            value = QLabel("0")
            value.setStyleSheet("font-size:28px;font-weight:800;color:#67A5FF;")
            v.addWidget(value)
            self.stat_labels[key] = value
            grid.addWidget(box, i // 3, i % 3)
        layout.addLayout(grid)
        info = QLabel("سير العمل: استيراد ← تحليل المشاهد ← تصدير ← فرز ← رفع اختياري")
        info.setStyleSheet("font-size:15px;color:#AAB6C5;padding:15px;")
        layout.addWidget(info)
        self.dashboard_log = QTextEdit()
        self.dashboard_log.setReadOnly(True)
        self.dashboard_log.setPlaceholderText("سيظهر هنا سجل آخر العمليات…")
        layout.addWidget(self.dashboard_log)

    def _build_splitter(self):
        layout = QVBoxLayout(self.splitter_tab)
        top = QGroupBox("مصدر الفيديو وإعدادات التحليل")
        form = QGridLayout(top)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("اختر فيديو المصدر…")
        choose = QPushButton("اختيار فيديو")
        choose.clicked.connect(self.choose_source)
        self.detector_combo = QComboBox()
        self.detector_combo.addItems(["Content", "Adaptive"])
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(1, 100)
        self.threshold_spin.setSingleStep(1)
        self.min_scene_spin = QDoubleSpinBox()
        self.min_scene_spin.setRange(0.05, 30)
        self.min_scene_spin.setSingleStep(0.05)
        self.min_scene_spin.setSuffix(" ثانية")
        self.auto_export_check = QCheckBox("تصدير تلقائي بعد انتهاء التحليل")
        self.analyze_btn = QPushButton("تحليل واكتشاف المشاهد")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self.analyze_video)
        self.export_btn = QPushButton("تصدير جميع المقاطع")
        self.export_btn.clicked.connect(self.export_scenes)
        self.workflow_btn = QPushButton("بدء سير العمل التلقائي")
        self.workflow_btn.setObjectName("primary")
        self.workflow_btn.clicked.connect(self.start_workflow)
        self.folder_btn = QPushButton("اختيار مجلد فيديوهات")
        self.folder_btn.clicked.connect(self.choose_video_folder)
        self.batch_btn = QPushButton("معالجة جميع الفيديوهات بالترتيب")
        self.batch_btn.setObjectName("primary")
        self.batch_btn.clicked.connect(self.start_batch)
        self.stop_batch_btn = QPushButton("إيقاف بعد الفيديو الحالي")
        self.stop_batch_btn.clicked.connect(self.stop_batch)
        self.stop_batch_btn.setEnabled(False)
        form.addWidget(QLabel("الفيديو"), 0, 0)
        form.addWidget(self.source_edit, 0, 1, 1, 3)
        form.addWidget(choose, 0, 4)
        form.addWidget(QLabel("نوع الكاشف"), 1, 0)
        form.addWidget(self.detector_combo, 1, 1)
        form.addWidget(QLabel("الحساسية"), 1, 2)
        form.addWidget(self.threshold_spin, 1, 3)
        form.addWidget(QLabel("أقل مدة للمشهد"), 2, 0)
        form.addWidget(self.min_scene_spin, 2, 1)
        form.addWidget(self.auto_export_check, 2, 2, 1, 2)
        form.addWidget(self.analyze_btn, 3, 0, 1, 2)
        form.addWidget(self.export_btn, 3, 2)
        form.addWidget(self.workflow_btn, 3, 3, 1, 2)
        form.addWidget(self.folder_btn, 4, 0, 1, 2)
        form.addWidget(self.batch_btn, 4, 2, 1, 2)
        form.addWidget(self.stop_batch_btn, 4, 4)
        self.queue_label = QLabel("قائمة الانتظار: لم يتم اختيار مجلد")
        form.addWidget(self.queue_label, 5, 0, 1, 5)
        layout.addWidget(top)

        dest_box = QGroupBox("وجهة التصدير")
        dest_row = QHBoxLayout(dest_box)
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_btn = QPushButton("اختيار مجلد الحفظ")
        self.output_btn.clicked.connect(self.choose_output)
        dest_row.addWidget(self.output_edit, 1)
        dest_row.addWidget(self.output_btn)
        layout.addWidget(dest_box)

        self.scene_table = QTableWidget(0, 4)
        self.scene_table.setHorizontalHeaderLabels(["رقم", "البداية", "النهاية", "المدة"])
        self.scene_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.scene_table, 1)

        progress_box = QGroupBox("تقدم العملية")
        p = QVBoxLayout(progress_box)
        self.operation_label = QLabel("بانتظار بدء عملية")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_detail = QLabel("لا توجد عملية نشطة")
        p.addWidget(self.operation_label)
        p.addWidget(self.progress_bar)
        p.addWidget(self.progress_detail)
        layout.addWidget(progress_box)

    def _build_sorter(self):
        layout = QVBoxLayout(self.sorter_tab)
        controls = QHBoxLayout()
        self.sort_folder_label = QLabel("مجلد المقاطع: غير محدد")
        reload_btn = QPushButton("إعادة تحميل المقاطع")
        reload_btn.clicked.connect(self._load_sort_list)
        controls.addWidget(self.sort_folder_label, 1)
        controls.addWidget(reload_btn)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        self.video_widget = QVideoWidget()
        lv.addWidget(self.video_widget, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(lambda *args: self._log("تعذر تشغيل الفيديو. تحقق من صيغة الملف أو الترميز."))
        play_row = QHBoxLayout()
        play = QPushButton("تشغيل / إيقاف")
        play.clicked.connect(self.toggle_play)
        play_row.addWidget(play)
        self.current_clip_label = QLabel("لا يوجد مقطع")
        play_row.addWidget(self.current_clip_label, 1)
        lv.addLayout(play_row)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.clip_list = QListWidget()
        self.clip_list.currentRowChanged.connect(self._select_sort_row)
        rv.addWidget(self.clip_list, 1)
        self.sort_progress = QLabel("0 / 0")
        rv.addWidget(self.sort_progress)
        buttons = QGridLayout()
        moving = QPushButton("سيارة متحركة  [1]")
        moving.clicked.connect(lambda: self.classify("MovingCars"))
        stopping = QPushButton("سيارة متوقفة  [2]")
        stopping.clicked.connect(lambda: self.classify("StoppingCars"))
        excluded = QPushButton("استبعاد  [3]")
        excluded.setObjectName("danger")
        excluded.clicked.connect(lambda: self.classify("ExcludedCars"))
        skip = QPushButton("تخطي  [Space]")
        skip.clicked.connect(self.skip_clip)
        undo = QPushButton("تراجع  [Ctrl+Z]")
        undo.clicked.connect(self.undo_sort)
        restore = QPushButton("استعادة آخر مقطع متخطى")
        restore.clicked.connect(self.restore_skipped)
        buttons.addWidget(moving, 0, 0)
        buttons.addWidget(stopping, 0, 1)
        buttons.addWidget(excluded, 1, 0)
        buttons.addWidget(skip, 1, 1)
        buttons.addWidget(undo, 2, 0)
        buttons.addWidget(restore, 2, 1)
        rv.addLayout(buttons)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([760, 380])
        layout.addWidget(splitter, 1)

    def _build_settings(self):
        layout = QVBoxLayout(self.settings_tab)
        box = QGroupBox("إعدادات الرفع إلى YouTube")
        form = QFormLayout(box)
        self.auto_upload_check = QCheckBox("تفعيل الرفع التلقائي بعد التصدير")
        self.client_secrets_edit = QLineEdit()
        self.client_secrets_edit.setPlaceholderText("ملف OAuth Client JSON")
        browse = QPushButton("اختيار ملف OAuth")
        browse.clicked.connect(self.choose_oauth)
        oauth_row = QHBoxLayout()
        oauth_row.addWidget(self.client_secrets_edit, 1)
        oauth_row.addWidget(browse)
        oauth_widget = QWidget()
        oauth_widget.setLayout(oauth_row)
        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(["private", "unlisted", "public"])
        self.title_prefix_edit = QLineEdit("Car Clip")
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(90)
        self.tags_edit = QLineEdit("cars, car edits")
        form.addRow(self.auto_upload_check)
        form.addRow("ملف OAuth", oauth_widget)
        form.addRow("خصوصية الفيديو", self.privacy_combo)
        form.addRow("بادئة العنوان", self.title_prefix_edit)
        form.addRow("الوصف", self.description_edit)
        form.addRow("الكلمات المفتاحية (افصل بينها بفواصل)", self.tags_edit)
        layout.addWidget(box)
        save = QPushButton("حفظ الإعدادات")
        save.setObjectName("primary")
        save.clicked.connect(self.save_all_settings)
        upload_now = QPushButton("رفع المقاطع المصدرة الآن")
        upload_now.clicked.connect(self.upload_exported)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(upload_now)
        layout.addLayout(row)
        note = QLabel("يتطلب الرفع إعداد OAuth من Google Cloud وتفعيل YouTube Data API v3. تُحفظ بيانات الدخول في macOS Keychain عند توفره.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#AAB6C5;padding:10px;")
        layout.addWidget(note)
        layout.addStretch()

    def _apply_settings(self):
        self.source_edit.setText(self.settings.get("last_source", ""))
        self.output_edit.setText(self.settings.get("output_dir", ""))
        self.detector_combo.setCurrentText(self.settings.get("detector", "Content"))
        self.threshold_spin.setValue(float(self.settings.get("threshold", 12.0)))
        self.min_scene_spin.setValue(float(self.settings.get("min_scene", 0.15)))
        self.auto_export_check.setChecked(bool(self.settings.get("auto_export", True)))
        self.auto_upload_check.setChecked(bool(self.settings.get("auto_upload", False)))
        self.client_secrets_edit.setText(self.settings.get("youtube_client_secrets", ""))
        self.privacy_combo.setCurrentText(self.settings.get("privacy", "private"))
        self.title_prefix_edit.setText(self.settings.get("upload_title_prefix", "Car Clip"))
        self.description_edit.setPlainText(self.settings.get("upload_description", ""))
        self.tags_edit.setText(", ".join(self.settings.get("upload_tags", [])))

    def save_all_settings(self):
        self.settings.update({
            "last_source": self.source_edit.text(),
            "output_dir": self.output_edit.text(),
            "detector": self.detector_combo.currentText(),
            "threshold": self.threshold_spin.value(),
            "min_scene": self.min_scene_spin.value(),
            "auto_export": self.auto_export_check.isChecked(),
            "auto_upload": self.auto_upload_check.isChecked(),
            "youtube_client_secrets": self.client_secrets_edit.text(),
            "privacy": self.privacy_combo.currentText(),
            "upload_title_prefix": self.title_prefix_edit.text(),
            "upload_description": self.description_edit.toPlainText(),
            "upload_tags": [x.strip() for x in self.tags_edit.text().split(",") if x.strip()],
        })
        save_settings(self.settings)
        self._log("تم حفظ الإعدادات.")
        self._refresh_stats()

    @staticmethod
    def _natural_sort_key(path):
        # Example: clip2.mp4 is sorted before clip10.mp4.
        return [int(part) if part.isdigit() else part.casefold()
                for part in re.split(r"(\d+)", Path(path).name)]

    def choose_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختيار مجلد الفيديوهات", str(Path.home()))
        if not folder:
            return
        supported = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
        self.video_queue = sorted(
            [str(item) for item in Path(folder).iterdir()
             if item.is_file() and item.suffix.lower() in supported],
            key=self._natural_sort_key
        )
        self.queue_index = 0
        self.batch_done = 0
        self.batch_total = len(self.video_queue)
        self.queue_label.setText(
            f"قائمة الانتظار: {len(self.video_queue)} فيديو — مرتبة حسب الاسم والترقيم"
        )
        self._log(f"تم استيراد {len(self.video_queue)} فيديو من: {folder}")
        if self.video_queue:
            self.source_edit.setText(self.video_queue[0])
        else:
            QMessageBox.information(self, "لا توجد فيديوهات",
                                    "لم يتم العثور على فيديوهات مدعومة في المجلد المحدد.")

    def start_batch(self):
        if self.batch_running:
            return
        if not self.video_queue:
            self.choose_video_folder()
        if not self.video_queue:
            return
        self.batch_running = True
        self.batch_stop_requested = False
        self.queue_index = 0
        self.batch_done = 0
        self.batch_total = len(self.video_queue)
        self.batch_btn.setEnabled(False)
        self.folder_btn.setEnabled(False)
        self.stop_batch_btn.setEnabled(True)
        self.auto_export_check.setChecked(True)
        self._log(f"بدء المعالجة المتتابعة لـ {self.batch_total} فيديو بالترتيب.")
        self._process_next_video()

    def stop_batch(self):
        if self.batch_running:
            self.batch_running = False
            self._log("تم طلب الإيقاف؛ لن يبدأ التطبيق فيديو جديداً بعد انتهاء الجاري.")
            self.stop_batch_btn.setEnabled(False)

    def _process_next_video(self):
        if not self.batch_running or getattr(self, "batch_stop_requested", False):
            self._finish_batch("تم إيقاف قائمة الفيديوهات بعد إكمال الفيديو الجاري.")
            return
        if self.queue_index >= self.batch_total:
            self._finish_batch("اكتملت معالجة جميع فيديوهات المجلد.")
            return
        source = self.video_queue[self.queue_index]
        self.source_edit.setText(source)
        self.settings["last_source"] = source
        save_settings(self.settings)
        self.scenes = []
        self.scene_table.setRowCount(0)
        self.progress_bar.setRange(0, 0)
        self.operation_label.setText(
            f"تحليل الفيديو {self.queue_index + 1}/{self.batch_total}: {Path(source).name}"
        )
        self.progress_detail.setText(f"اكتمل {self.batch_done} من {self.batch_total} فيديو")
        self._log(f"تحليل {self.queue_index + 1}/{self.batch_total}: {Path(source).name}")
        self._start_scene_worker(source)

    def _start_scene_worker(self, source):
        self.scene_worker = SceneWorker(source, self.detector_combo.currentText(),
                                        self.threshold_spin.value(), self.min_scene_spin.value())
        self.scene_worker.progress.connect(self._set_operation)
        self.scene_worker.finished_scenes.connect(self._scenes_ready)
        self.scene_worker.failed.connect(self._operation_failed)
        self.scene_worker.start()

    def _advance_batch(self):
        self.batch_done += 1
        self.queue_index += 1
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(self.batch_done / max(self.batch_total, 1) * 100))
        self.progress_detail.setText(f"اكتمل {self.batch_done} من {self.batch_total} فيديو")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(250, self._process_next_video)

    def _finish_batch(self, message):
        self.batch_running = False
        self.batch_btn.setEnabled(True)
        self.folder_btn.setEnabled(True)
        self.stop_batch_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(self.batch_done / max(self.batch_total, 1) * 100))
        self.operation_label.setText(message)
        self.progress_detail.setText(f"تمت معالجة {self.batch_done} من {self.batch_total} فيديو")
        self.status_label.setText("جاهز للعمل")
        self._log(message)
        QMessageBox.information(self, "انتهاء المعالجة", message +
                                f"\nتمت معالجة {self.batch_done} من {self.batch_total} فيديو.")

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار فيديو", "", "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v)")
        if path:
            self.source_edit.setText(path)
            self.settings["last_source"] = path
            save_settings(self.settings)
            self._log(f"تم اختيار المصدر: {Path(path).name}")

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "اختيار مجلد حفظ المقاطع", self.output_edit.text() or str(Path.home()))
        if path:
            self.output_edit.setText(path)
            self.settings["output_dir"] = path
            save_settings(self.settings)
            self._load_sort_list()

    def choose_oauth(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف OAuth Client", "", "JSON Files (*.json)")
        if path:
            self.client_secrets_edit.setText(path)

    def analyze_video(self):
        source = self.source_edit.text().strip()
        if not source or not Path(source).is_file():
            QMessageBox.warning(self, "مصدر غير صالح", "اختر ملف فيديو صالحاً أولاً.")
            return
        if self.scene_worker and self.scene_worker.isRunning():
            return
        self.save_all_settings()
        self._set_busy(True, "تحليل الفيديو واكتشاف المشاهد…", indeterminate=True)
        self._start_scene_worker(source)

    def _scenes_ready(self, scenes):
        self.scenes = scenes
        self.scene_table.setRowCount(len(scenes))
        for row, scene in enumerate(scenes):
            values = [str(scene["number"]), self._time(scene["start"]),
                      self._time(scene["end"]), f'{scene["duration"]:.2f} s']
            for col, value in enumerate(values):
                self.scene_table.setItem(row, col, QTableWidgetItem(value))
        self.stat_labels["scenes"].setText(str(len(scenes)))
        self._log(f"اكتمل التحليل: تم اكتشاف {len(scenes)} مشهداً.")
        if self.batch_running:
            if scenes:
                self.export_scenes()
            else:
                self._log("لم يتم العثور على مشاهد صالحة؛ الانتقال إلى الفيديو التالي.")
                self._advance_batch()
            return
        self._set_busy(False, "اكتمل تحليل الفيديو", 100)
        if self.auto_export_check.isChecked() and scenes:
            self.export_scenes()

    def export_scenes(self):
        if not self.scenes:
            QMessageBox.information(self, "لا توجد مشاهد", "حلّل الفيديو أولاً.")
            return
        source = self.source_edit.text().strip()
        output = self.output_edit.text().strip()
        if not output:
            self.choose_output()
            output = self.output_edit.text().strip()
        if not output:
            return
        self.save_all_settings()
        if self.export_worker and self.export_worker.isRunning():
            return
        self._set_busy(True, "بدء تصدير المقاطع…", 0)
        clips_output = Path(output) / "ClipsCars"
        clips_output.mkdir(parents=True, exist_ok=True)
        self.export_worker = ExportWorker(source, self.scenes, clips_output)
        self.export_worker.progress.connect(self._export_progress)
        self.export_worker.log.connect(self._log)
        self.export_worker.completed.connect(self._export_done)
        self.export_worker.failed.connect(self._operation_failed)
        self.export_worker.start()

    def _export_progress(self, index, total, name, pct):
        overall = int(((index - 1 + pct / 100) / max(total, 1)) * 100)
        self.progress_bar.setValue(overall)
        self.operation_label.setText(f"تصدير: {name}")
        self.progress_detail.setText(f"المقطع {index} من {total} — {pct:.0f}%")

    def _export_done(self, paths):
        self.exported = paths
        self.stat_labels["exported"].setText(str(len(paths)))
        self._log(f"اكتمل التصدير: {len(paths)} ملفاً.")
        self._set_busy(False, "اكتمل التصدير", 100)
        self._load_sort_list()
        if self.auto_upload_check.isChecked() and paths:
            if self.batch_running:
                self._batch_waiting_for_upload = True
            self.upload_paths(paths)
            return
        if self.batch_running:
            self._advance_batch()

    def start_workflow(self):
        if not self.source_edit.text().strip():
            self.choose_source()
        if self.source_edit.text().strip():
            self.auto_export_check.setChecked(True)
            self.save_all_settings()
            self._log("بدأ سير العمل: تحليل ثم تصدير، ثم رفع اختياري.")
            self.analyze_video()

    def upload_exported(self):
        paths = self.exported or [str(p) for p in Path(self.output_edit.text()).glob("*.mp4")]
        if not paths:
            QMessageBox.information(self, "لا توجد ملفات", "لا توجد مقاطع مصدرة لرفعها.")
            return
        self.upload_paths(paths)

    def upload_paths(self, paths):
        secrets = self.client_secrets_edit.text().strip()
        if not secrets or not Path(secrets).is_file():
            QMessageBox.warning(self, "إعداد OAuth مطلوب", "اختر ملف OAuth Client JSON أولاً.")
            self.tabs.setCurrentWidget(self.settings_tab)
            return
        self.save_all_settings()
        self.upload_worker = UploadWorker(paths, secrets, self.privacy_combo.currentText(),
                                           self.title_prefix_edit.text(),
                                           self.description_edit.toPlainText(),
                                           [x.strip() for x in self.tags_edit.text().split(",") if x.strip()])
        self.upload_worker.progress.connect(self._set_operation)
        self.upload_worker.completed.connect(self._upload_done)
        self.upload_worker.failed.connect(self._operation_failed)
        self._set_busy(True, "بدء رفع الفيديوهات…", indeterminate=True)
        self.upload_worker.start()

    def _upload_done(self, success, total):
        self.stat_labels["uploads"].setText(str(success))
        self._log(f"انتهى الرفع: {success} من {total} فيديو.")
        self._set_busy(False, "انتهى الرفع", 100)
        if self.batch_running and getattr(self, "_batch_waiting_for_upload", False):
            self._batch_waiting_for_upload = False
            self._advance_batch()

    def _operation_failed(self, message):
        self._set_busy(False, "حدث خطأ", 0)
        self._log("خطأ: " + message.splitlines()[0])
        QMessageBox.critical(self, "تعذر إكمال العملية", message[:3000])
        if self.batch_running:
            self._log("تم تجاوز الفيديو الذي فشل، وسيتم الانتقال إلى الفيديو التالي.")
            self._batch_waiting_for_upload = False
            self._advance_batch()

    def _set_busy(self, busy, label="", value=None, indeterminate=False):
        self.status_label.setText("قيد التنفيذ…" if busy else "جاهز للعمل")
        self.operation_label.setText(label or ("قيد التنفيذ…" if busy else "بانتظار بدء عملية"))
        if indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            if value is not None:
                self.progress_bar.setValue(value)
        self.analyze_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy)
        self.workflow_btn.setEnabled(not busy)

    def _set_operation(self, text):
        self.operation_label.setText(text)
        self.progress_detail.setText(text)
        self._log(text)

    def _log(self, text):
        from datetime import datetime
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
        self.dashboard_log.append(line)

    def _load_sort_list(self):
        base = Path(self.output_edit.text() or self.settings.get("output_dir", ""))
        folder = base / "ClipsCars"
        if not folder.exists():
            folder = base
        self.sort_files = sorted([p for p in folder.glob("*") if p.suffix.lower() in
                                  {".mp4", ".mov", ".mkv", ".avi", ".m4v"}])
        self.clip_list.blockSignals(True)
        self.clip_list.clear()
        for path in self.sort_files:
            self.clip_list.addItem(path.name)
        self.clip_list.blockSignals(False)
        self.sort_folder_label.setText(f"مجلد المقاطع: {folder}")
        self.sort_index = 0
        self._show_sort_clip()

    def _select_sort_row(self, row):
        if 0 <= row < len(self.sort_files):
            self.sort_index = row
            self._show_sort_clip()

    def _show_sort_clip(self):
        if not self.sort_files:
            self.current_clip_label.setText("لا توجد مقاطع في مجلد ClipsCars")
            self.sort_progress.setText("0 / 0")
            self.player.stop()
            return
        self.sort_index = max(0, min(self.sort_index, len(self.sort_files)-1))
        path = self.sort_files[self.sort_index]
        self.current_clip_label.setText(path.name)
        self.sort_progress.setText(f"{self.sort_index + 1} / {len(self.sort_files)}")
        self.clip_list.setCurrentRow(self.sort_index)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def classify(self, category):
        if not self.sort_files:
            return
        source = self.sort_files[self.sort_index]
        base = Path(self.output_edit.text())
        destination_dir = base / category
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        if destination.exists():
            QMessageBox.warning(self, "الملف موجود", f"يوجد ملف بالاسم نفسه داخل {category}.")
            return
        self.player.stop()
        shutil.move(str(source), str(destination))
        self.undo_stack.append((str(destination), str(source)))
        self._log(f"تم تصنيف {source.name} إلى {category}.")
        self._refresh_stats()
        self._load_sort_list()

    def skip_clip(self):
        if not self.sort_files:
            return
        skipped_path = self.sort_files.pop(self.sort_index)
        self.skipped.append(str(skipped_path))
        self._log(f"تم تخطي {skipped_path.name} مؤقتاً.")
        self.clip_list.blockSignals(True)
        self.clip_list.takeItem(self.sort_index)
        self.clip_list.blockSignals(False)
        if self.sort_files:
            self.sort_index = min(self.sort_index, len(self.sort_files) - 1)
            self._show_sort_clip()
        else:
            self.current_clip_label.setText("لا توجد مقاطع أخرى — يمكنك استعادة المقاطع المتخطاة")
            self.sort_progress.setText("0 / 0")
            self.player.stop()

    def restore_skipped(self):
        if not self.skipped:
            QMessageBox.information(self, "لا توجد مقاطع متخطاة", "قائمة المقاطع المتخطاة فارغة.")
            return
        path = Path(self.skipped.pop())
        if path.is_file():
            self.sort_files.append(path)
            self.sort_files.sort()
            self.clip_list.blockSignals(True)
            self.clip_list.clear()
            for item in self.sort_files:
                self.clip_list.addItem(item.name)
            self.clip_list.blockSignals(False)
            self.sort_index = self.sort_files.index(path)
            self._log(f"تمت استعادة المقطع المتخطى: {path.name}")
            self._show_sort_clip()
        else:
            QMessageBox.warning(self, "المقطع غير موجود", "لم يعد الملف المتخطى موجوداً في مجلده الأصلي.")

    def undo_sort(self):
        if not self.undo_stack:
            return
        destination, source = self.undo_stack.pop()
        try:
            Path(source).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(destination, source)
            self._log(f"تم التراجع عن تصنيف {Path(source).name}.")
            self._load_sort_list()
            self._refresh_stats()
        except Exception as exc:
            QMessageBox.warning(self, "تعذر التراجع", str(exc))

    def _refresh_stats(self):
        base = Path(self.output_edit.text() or self.settings.get("output_dir", ""))
        for key, folder in [("moving", "MovingCars"), ("stopping", "StoppingCars"), ("excluded", "ExcludedCars")]:
            count = len(list((base / folder).glob("*"))) if (base / folder).exists() else 0
            self.stat_labels[key].setText(str(count))

    def _time(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}"

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_1:
            self.classify("MovingCars")
        elif event.key() == Qt.Key_2:
            self.classify("StoppingCars")
        elif event.key() == Qt.Key_3:
            self.classify("ExcludedCars")
        elif event.key() == Qt.Key_Space and self.tabs.currentWidget() == self.sorter_tab:
            self.skip_clip()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.save_all_settings()
        for worker in (self.scene_worker, self.export_worker, self.upload_worker):
            if worker and worker.isRunning():
                worker.requestInterruption()
        self.player.stop()
        event.accept()
