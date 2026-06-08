"""
TTS 引擎封装 — 自动匹配中文语音，每次朗读前重建引擎解决 SAPI5 多次调用僵死问题。
"""
import threading


class TTSEngine:

    def __init__(self):
        self.engine = None
        self.available = False
        self.voice_name = ""
        self.rate = 160
        self._init()

    # ------------------------------------------------------------------
    def _init(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty('voices')
            keywords = ['Huihui', 'HuiHui', 'Yaoyao', 'Kangkang',
                        'Zira', 'Hanhan', 'zh-CN', 'Chinese', 'chinese',
                        '中文', 'Mandarin']  # 中文
            for kw in keywords:
                for v in voices:
                    if kw.lower() in v.name.lower():
                        self.engine.setProperty('voice', v.id)
                        self.voice_name = v.name
                        break
                if self.voice_name:
                    break
            if not self.voice_name and voices:
                self.voice_name = voices[0].name
            self.engine.setProperty('rate', self.rate)
            self.available = True
        except Exception as e:
            print(f"[TTS] {e}")

    # ------------------------------------------------------------------
    def say(self, text):
        if self.engine:
            self.engine.say(text)

    def run_and_wait(self):
        if self.engine:
            self.engine.runAndWait()

    def stop(self):
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass

    def reset(self):
        """Windows SAPI5 多次 runAndWait 后引擎僵死，每次朗读前重建。"""
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
            self.engine = None
            self.available = False
        self._init()

    def set_rate(self, rate):
        self.rate = max(50, min(400, rate))
        if self.engine:
            self.engine.setProperty('rate', self.rate)

    def adjust(self, delta):
        self.set_rate(self.rate + delta)

    # ------------------------------------------------------------------
    def speak(self, text):
        """在后台线程中朗读文本，完成后回调 on_done（主线程）。"""
        if not self.available or not text:
            return

        def _run():
            try:
                self.reset()
                if not self.available:
                    return
                self.say(text)
                self.run_and_wait()
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t
