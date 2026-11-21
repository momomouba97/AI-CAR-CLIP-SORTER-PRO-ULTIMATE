from PySide6.QtCore import QThread, Signal
from pathlib import Path
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector, AdaptiveDetector
from .ffmpeg import export_clip
import traceback

class SceneWorker(QThread):
    progress = Signal(str)
    finished_scenes = Signal(list)
    failed = Signal(str)

    def __init__(self, source, detector, threshold, min_scene):
        super().__init__()
        self.source = source
        self.detector = detector
        self.threshold = threshold
        self.min_scene = min_scene

    def run(self):
        try:
            self.progress.emit("فتح الفيديو وقراءة معلوماته…")
            video = open_video(self.source)
            manager = SceneManager()
            min_frames = max(1, int(video.frame_rate * self.min_scene))
            if self.detector == "Adaptive":
                manager.add_detector(AdaptiveDetector(adaptive_threshold=self.threshold,
                                                       min_scene_len=min_frames))
            else:
                manager.add_detector(ContentDetector(threshold=self.threshold,
                                                      min_scene_len=min_frames))
            self.progress.emit("تحليل الفيديو واكتشاف تغيّر المشاهد…")
            manager.detect_scenes(video=video, show_progress=False)
            scenes = manager.get_scene_list()
            result = []
            for index, (start, end) in enumerate(scenes, 1):
                start_s, end_s = start.get_seconds(), end.get_seconds()
                if end_s > start_s:
                    result.append({
                        "number": index,
                        "start": start_s,
                        "end": end_s,
                        "duration": end_s - start_s
                    })
            self.finished_scenes.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")

class ExportWorker(QThread):
    progress = Signal(int, int, str, float)
    log = Signal(str)
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, source, scenes, output_dir, crf=18):
        super().__init__()
        self.source = Path(source)
        self.scenes = scenes
        self.output_dir = Path(output_dir)
        self.crf = crf
        self._stop = False
        self.exported = []

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            total = len(self.scenes)
            for i, scene in enumerate(self.scenes, 1):
                if self._stop:
                    self.log.emit("تم إيقاف التصدير بناءً على طلب المستخدم.")
                    break
                name = f"{self.source.stem}_clip_{i:04d}.mp4"
                target = self.output_dir / name
                if target.exists():
                    suffix = 1
                    while target.exists():
                        target = self.output_dir / f"{self.source.stem}_clip_{i:04d}_{suffix}.mp4"
                        suffix += 1
                self.log.emit(f"تصدير {name}")
                for pct in export_clip(self.source, target, scene["start"],
                                       scene["duration"], self.crf):
                    self.progress.emit(i, total, name, pct)
                self.exported.append(str(target))
            self.completed.emit(self.exported)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")

class UploadWorker(QThread):
    progress = Signal(str)
    completed = Signal(int, int)
    failed = Signal(str)

    def __init__(self, paths, client_secrets, privacy="private", title_prefix="Car Clip",
                 description="", tags=None):
        super().__init__()
        self.paths = [str(p) for p in paths]
        self.client_secrets = client_secrets
        self.privacy = privacy
        self.title_prefix = title_prefix
        self.description = description
        self.tags = tags or []

    def run(self):
        try:
            import json
            import keyring
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            scopes = ["https://www.googleapis.com/auth/youtube.upload"]
            token_json = keyring.get_password("AICarClipSorter", "youtube_oauth")
            creds = None
            if token_json:
                try:
                    creds = Credentials.from_authorized_user_info(json.loads(token_json), scopes)
                except Exception:
                    creds = None
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if not creds or not creds.valid:
                self.progress.emit("سيتم فتح المتصفح لإتمام تسجيل الدخول إلى YouTube…")
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets, scopes)
                creds = flow.run_local_server(port=0, open_browser=True)
                keyring.set_password("AICarClipSorter", "youtube_oauth", creds.to_json())

            service = build("youtube", "v3", credentials=creds)
            success = 0
            for index, path in enumerate(self.paths, 1):
                self.progress.emit(f"رفع {index}/{len(self.paths)}: {Path(path).name}")
                body = {
                    "snippet": {
                        "title": f"{self.title_prefix} - {Path(path).stem}"[:100],
                        "description": self.description,
                        "tags": self.tags[:500],
                        "categoryId": "2"
                    },
                    "status": {"privacyStatus": self.privacy}
                }
                media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True)
                request = service.videos().insert(part="snippet,status", body=body, media_body=media)
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        self.progress.emit(f"رفع {Path(path).name}: {int(status.progress() * 100)}%")
                success += 1
            self.completed.emit(success, len(self.paths))
        except Exception as exc:
            self.failed.emit(str(exc))
