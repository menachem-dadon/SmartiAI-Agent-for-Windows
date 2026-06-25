"""First-run legal agreement gate for Smarti."""
from .common import *
from .ui_styles import *
from .ui_controls import make_circular_pixmap
from PyQt6.QtWidgets import QTextBrowser


LEGAL_AGREEMENT_TEXT = f"""
{LEGAL_AGREEMENT_TITLE}
תאריך תחילה: {LEGAL_AGREEMENT_EFFECTIVE_DATE}
גרסת מסמך: {LEGAL_AGREEMENT_VERSION}

חשוב: מסמך זה מנוסח כתנאי שימוש, מדיניות פרטיות וכתב ויתור למוצר תוכנה שולחני. הוא אינו מחליף ייעוץ משפטי פרטני. השימוש ב-Smarti AI Agent for Windows ("Smarti", "התוכנה" או "המערכת") מותר רק לאחר קריאה והסכמה מפורשת למסמך זה.

1. קבלת התנאים
בלחיצה על "אני מסכים" המשתמש מאשר כי קרא, הבין וקיבל על עצמו את כל התנאים המפורטים במסמך זה, לרבות מדיניות הפרטיות, מגבלות האחריות, כתב הוויתור והוראות השימוש. אם אינך מסכים לכל התנאים, אין להשתמש בתוכנה ועליך לסגור אותה. המשך שימוש בתוכנה לאחר עדכון מסמך זה כפוף להסכמה לגרסה העדכנית שתוצג.

2. מהות התוכנה
Smarti היא תוכנת עזר מקומית למחשב Windows המאפשרת שיחה עם מודלי בינה מלאכותית, ניהול הקשר וזיכרון מקומי, שימוש בכלים מקומיים וחיצוניים, קריאה ויצירה של קבצים, חיפוש באינטרנט, אוטומציה של דפדפן או שולחן עבודה, עבודה עם אימיילים, התקנת הרחבות, והרצת פעולות נוספות בהתאם להגדרות המשתמש ולהרשאות שניתנו. התוכנה אינה אדם, אינה בעלת שיקול דעת מקצועי, ואינה מהווה תחליף לבדיקה אנושית, לייעוץ מקצועי או למערכת בקרה מוסמכת.

3. אחריות המשתמש
המשתמש אחראי באופן מלא ובלעדי לכל פעולה, הוראה, קובץ, נתון, חיבור, הרשאה, מפתח API, חשבון צד שלישי, התקנה, אוטומציה, פקודה, שימוש בתוצאה, הסתמכות על פלט או החלטה המתבצעים באמצעות התוכנה או בעקבותיה. על המשתמש לבדוק מראש כל פעולה בעלת משמעות, לשמור גיבויים עדכניים, לוודא הרשאות חוקיות לשימוש במידע ובמערכות, ולהימנע מהפעלת התוכנה בסביבות שבהן טעות, עיכוב או פעולה לא צפויה עלולים לגרום נזק מהותי.

4. אין ייעוץ מקצועי
כל פלט של התוכנה, לרבות טקסט, קוד, המלצה, ניתוח, סיכום, תרגום, פעולה אוטומטית, חיפוש או תשובה, ניתן למטרות עזר כלליות בלבד. אין לראות בתוכנה או בפלטיה ייעוץ משפטי, רפואי, פיננסי, חשבונאי, בטיחותי, אבטחתי, הנדסי, תעסוקתי, רגולטורי או מקצועי אחר. לפני הסתמכות על פלט בתחום בעל משמעות מקצועית או סיכון, חובה לקבל ייעוץ מאיש מקצוע מוסמך ולבצע אימות עצמאי.

5. מגבלות AI ואוטומציה
מודלי AI וכלי אוטומציה עלולים לטעות, להמציא מידע, לפרש הוראות באופן שגוי, להפעיל כלי לא מתאים, ליצור קוד פגום, למחוק או לשנות מידע, לשלוח תוכן לא רצוי, לבצע פעולה באתר או בתוכנה אחרת, או להפיק תוצאה חלקית, מיושנת, מטעה, בלתי חוקית, מפרת זכויות או בלתי הולמת. המשתמש מאשר כי ידועים לו סיכונים אלה וכי הוא משתמש בתוכנה ובפלטיה על אחריותו בלבד.

6. פעולות מקומיות, קבצים והרצת קוד
התוכנה עשויה, בהתאם להגדרות ולהרשאות, לקרוא קבצים, ליצור קבצים, לשנות קבצים, להריץ פקודות Shell, להפעיל סקריפטים, להתקין חבילות, להשתמש בכלים חיצוניים, לבצע אוטומציה בממשק Windows, ולפעול בדפדפן או בתוכנות אחרות. פעולות כאלה עלולות לגרום לאובדן מידע, שיבוש מערכת, שינוי בלתי רצוי, חשיפה של מידע, תקלות אבטחה, עלויות צד שלישי או הפרת תנאים של שירותים אחרים. המשתמש אחראי לוודא שכל פעולה בטוחה, מורשית ונחוצה.

7. שירותי צד שלישי
התוכנה יכולה להתחבר לספקי מודלי AI, מנועי חיפוש, שירותי אימייל, אתרים, ממשקי API, כלי MCP, Skills, חבילות תוכנה, דפדפנים ושירותים חיצוניים נוספים. שירותים אלה אינם בשליטת יוצר התוכנה ועשויים להיות כפופים לתנאי שימוש, מדיניות פרטיות, מגבלות, עלויות, שמירת נתונים, זמינות ושינויים משלהם. יוצר התוכנה אינו אחראי לפעולה, זמינות, אבטחה, תוכן, דיוק, חיובים, אובדן נתונים או מדיניות של צדדים שלישיים.

8. מידע שנשמר מקומית
Smarti עשויה לשמור במחשב המשתמש נתונים כגון הגדרות, העדפות, היסטוריית שיחה, זיכרון מקומי, נתוני שימוש, לוגים, יומני אודיט, קבצים מצורפים, קבצי פלט, תצורת כלים, הרחבות, מידע על משימות רקע, הגדרות אימייל, נתיבי קבצים ומידע טכני הדרוש להפעלת התוכנה. כברירת מחדל, נתוני runtime נשמרים בתיקיית המשתמש של SmartiAI תחת Windows, וקבצי פלט עשויים להישמר בתיקיית Smarti_Outputs או בתיקייה אחרת שהמשתמש הגדיר.

9. מפתחות, סודות ונתוני התחברות
התוכנה עשויה לשמור או להשתמש במפתחות API, סיסמאות אפליקציה, אסימונים או פרטי התחברות שהמשתמש הזין. התוכנה כוללת מנגנוני שמירה והסתרה מסוימים, אך אין התחייבות להגנה מוחלטת. המשתמש אחראי להשתמש במפתחות מוגבלים, לשמור על סודיותם, לבטל מפתחות שנחשפו, לבדוק הרשאות ועלויות, ולהימנע מהזנת סודות שאין לו זכות להשתמש בהם.

10. שליחת מידע לצדדים שלישיים
כאשר המשתמש משתמש במודל חיצוני, חיפוש רשת, אימייל, אתר, API, כלי חיצוני או הרחבה, התוכנה עשויה לשלוח לצדדים שלישיים את הטקסט, הקבצים, ההוראות, תוצאות הכלים, מטא-דאטה או מידע אחר הדרוש לביצוע הפעולה. גם אם קיימות בקשות אישור או הגדרות פרטיות, האחריות לבדוק מה נשלח, לאן, ולפי אילו תנאים היא של המשתמש. אין להזין או לשלוח מידע אישי, סודי, רפואי, פיננסי, משפטי, עסקי, מוגן בזכויות או רגיש אחר אלא אם המשתמש מוסמך לכך ומבין את הסיכון.

11. לוגים, אבטחה ופרטיות
התוכנה עשויה ליצור לוגים לצורך תפעול, אבחון, אודיט ושיפור שימושיות. קיימות הגדרות לצמצום או טשטוש מידע רגיש בלוגים, אך ייתכן שמידע מסוים עדיין יישמר או יופיע בקבצים מקומיים, בתוצרי פלט, בשירותי צד שלישי או בזיכרון התוכנה. המשתמש אחראי לאבטחת המחשב, חשבון Windows, הרשאות הקבצים, גיבויים, הצפנה, אנטי-וירוס, גישה פיזית, ותצורת שירותי צד שלישי.

12. שמירה, מחיקה וניידות נתונים
המשתמש יכול למחוק או לגבות קבצים מקומיים של Smarti בהתאם למיקומי השמירה במחשב ולהגדרות שבחר. מחיקת נתונים מקומיים עשויה שלא למחוק מידע שכבר נשלח לספקי צד שלישי, נשמר בגיבויים, נכלל בלוגים חיצוניים או נשמר בחשבונות המשתמש אצל ספקים אחרים. מדיניות השמירה והמחיקה של צדדים שלישיים נקבעת על ידם בלבד.

13. שימושים אסורים
אין להשתמש בתוכנה לביצוע פעולה בלתי חוקית, פוגענית, מטעה, מפרת פרטיות, מפרת זכויות, מסכנת חיים, מסכנת מערכות, עוקפת אבטחה, מפיצה נוזקה, אוספת מידע ללא הרשאה, שולחת ספאם, מתחזה לאחר, מפרה תנאי שירות של צד שלישי, או יוצרת החלטות אוטומטיות בעלות השפעה מהותית על אדם ללא פיקוח אנושי והרשאה מתאימה.

14. אין אחריות
התוכנה מסופקת "כמות שהיא" ו"ככל שזמינה", ללא כל מצג או אחריות מכל סוג, מפורשת או משתמעת, לרבות אחריות לסחירות, התאמה למטרה מסוימת, דיוק, זמינות, רציפות, אבטחה, אי-הפרה, תאימות, תוצאה עסקית, שחזור מידע או היעדר תקלות. ייתכנו שגיאות, השבתות, אובדן מידע, אי-תאימות, תוצאות לא צפויות ושינויים ללא הודעה מוקדמת.

15. הגבלת אחריות
במידה המרבית המותרת לפי כל דין, יוצר התוכנה, מפיציה, תורמיה, בעליה, עובדיה, נציגיה, ספקיה ומי מטעמם לא יישאו באחריות לכל נזק, הפסד, הוצאה, תביעה או חבות מכל סוג, בין ישירים ובין עקיפים, מיוחדים, תוצאתיים, עונשיים, נלווים או מקריים, לרבות אובדן רווחים, הכנסות, מוניטין, נתונים, קבצים, סודות מסחריים, פרטיות, הזדמנויות עסקיות, שימוש במערכת, זמן עבודה, עלויות שחזור, עלויות שירותי צד שלישי, חיובי API, פגיעה במכשיר, פגיעה באבטחה, הפרת זכויות, תביעות צד שלישי או כל נזק אחר הנובע משימוש בתוכנה, מאי-יכולת להשתמש בה, מפלטיה, מהסתמכות עליה, מהגדרות המשתמש, מפעולות אוטומטיות, מקוד שנוצר או הורץ, או משירותי צד שלישי, אף אם נמסרה הודעה על אפשרות לנזק כזה.

16. שיפוי
המשתמש מתחייב לשפות ולהגן על יוצר התוכנה ומי מטעמו מפני כל טענה, דרישה, הפסד, נזק, אחריות, עלות או הוצאה, לרבות הוצאות משפטיות סבירות, הנובעים משימוש המשתמש בתוכנה, מהפרת תנאים אלה, מהפרת דין או זכויות צד שלישי, מהזנת מידע ללא הרשאה, מהפעלת כלים או אוטומציות, או מהסתמכות המשתמש או צד שלישי על פלטי התוכנה.

17. עדכונים ושינויים
התוכנה והמסמך עשויים להשתנות מעת לעת. ייתכן שעדכון יחייב הסכמה מחודשת לפני המשך שימוש. אם הוראה כלשהי במסמך זה תיחשב בלתי אכיפה, יתר ההוראות ימשיכו לחול במידה המרבית המותרת לפי הדין.

18. אישור המשתמש
בלחיצה על "אני מסכים" המשתמש מאשר כי הוא מבין שהתוכנה יכולה להשפיע על קבצים, חשבונות, שירותים, מידע ומערכות; כי אין הבטחה לתוצאה נכונה או בטוחה; כי עליו להפעיל שיקול דעת, פיקוח וגיבויים; וכי השימוש בתוכנה נעשה באחריותו הבלעדית ובכפוף לכל התנאים שלעיל.
""".strip()


def has_current_legal_acceptance(settings):
    acceptance = settings.get("legal_acceptance") if isinstance(settings, dict) else {}
    if not isinstance(acceptance, dict):
        return False
    return bool(acceptance.get("accepted")) and acceptance.get("version") == LEGAL_AGREEMENT_VERSION


def raw_settings_have_current_legal_acceptance():
    try:
        if not os.path.exists(SETTINGS_FILE):
            return False
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return has_current_legal_acceptance(json.load(f))
    except Exception as e:
        logging.warning(f"Legal acceptance check failed; requiring agreement: {e}")
        return False


def mark_legal_acceptance(settings):
    settings["legal_acceptance"] = {
        "accepted": True,
        "version": LEGAL_AGREEMENT_VERSION,
        "accepted_at": datetime.now().isoformat(timespec="seconds"),
        "accepted_app_version": APP_VERSION,
        "document_title": LEGAL_AGREEMENT_TITLE,
    }
    return settings


def record_legal_acceptance(core):
    mark_legal_acceptance(core.settings)
    core._save_settings()
    logger = getattr(core, "audit_logger", None)
    if logger:
        logger.record(
            "legal_agreement_accepted",
            {
                "version": LEGAL_AGREEMENT_VERSION,
                "app_version": APP_VERSION,
            },
            core.settings,
        )


class LegalAgreementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("אישור תנאי שימוש ופרטיות")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        surface = QFrame()
        surface.setObjectName("LegalSurface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(16, 16, 16, 14)
        surface_layout.setSpacing(12)
        layout.addWidget(surface)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.logo_lbl = QLabel()
        self.logo_lbl.setObjectName("LegalLogo")
        self.logo_lbl.setFixedSize(48, 48)
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            pixmap = make_circular_pixmap(logo_path, 48, border_color=LINE_COLOR, border_width=1, bg_color=PANEL_COLOR, focus_content=True)
            if pixmap:
                self.logo_lbl.setPixmap(pixmap)
        if self.logo_lbl.pixmap() is None:
            self.logo_lbl.setText("S")
            self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.logo_lbl, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title = QLabel("מדיניות פרטיות ותנאי שימוש")
        title.setObjectName("LegalTitle")
        title.setWordWrap(True)
        meta = QLabel(f"SmartiAI • גרסת מסמך {LEGAL_AGREEMENT_VERSION}")
        meta.setObjectName("LegalMeta")
        meta.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(meta)
        header.addLayout(title_col, 1)
        surface_layout.addLayout(header)

        intro = QLabel("לפני הכניסה הראשונה לצ'אט נדרש אישור מפורש. בלי אישור, סמארטי ייסגר ולא ימשיך להפעלה.")
        intro.setObjectName("LegalIntro")
        intro.setWordWrap(True)
        surface_layout.addWidget(intro)

        self.document_view = QTextBrowser()
        self.document_view.setObjectName("LegalDocument")
        self.document_view.setReadOnly(True)
        self.document_view.setOpenExternalLinks(False)
        self.document_view.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.document_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        option = self.document_view.document().defaultTextOption()
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setAlignment(Qt.AlignmentFlag.AlignRight)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        self.document_view.document().setDefaultTextOption(option)
        self.document_view.setPlainText(LEGAL_AGREEMENT_TEXT)
        self.document_view.verticalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        self.document_view.horizontalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        surface_layout.addWidget(self.document_view, 1)

        self.confirm_checkbox = QCheckBox("קראתי את המסמך ואני מאשר/ת שאני מסכים/ה לכל תנאיו")
        self.confirm_checkbox.setObjectName("LegalConfirmCheck")
        self.confirm_checkbox.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.confirm_checkbox.toggled.connect(self._set_agree_enabled)
        surface_layout.addWidget(self.confirm_checkbox)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.decline_button = QPushButton("לא מסכים - סגור")
        self.decline_button.setObjectName("LegalDeclineButton")
        self.decline_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.decline_button.clicked.connect(self.reject)

        self.agree_button = QPushButton("אני מסכים")
        self.agree_button.setObjectName("LegalAgreeButton")
        self.agree_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.agree_button.setEnabled(False)
        self.agree_button.clicked.connect(self.accept)
        button_row.addWidget(self.decline_button, 1)
        button_row.addWidget(self.agree_button, 1)

        surface_layout.addLayout(button_row)
        self._fit_to_smarti_window()

    def _set_agree_enabled(self, checked):
        self.agree_button.setEnabled(bool(checked))

    def reject(self):
        super().reject()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_to_smarti_window)

    def _fit_to_smarti_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available:
            max_w = min(450, max(340, available.width() - 28))
            max_h = min(740, max(500, available.height() - 34))
            target_w = min(430, max_w)
            target_h = min(700, max_h)
            min_w = min(360, target_w)
            min_h = min(520, target_h)
            self.setMinimumSize(min_w, min_h)
            self.setMaximumSize(max_w, max_h)
            self.resize(target_w, target_h)
            self.move(
                available.x() + max(0, (available.width() - self.width()) // 2),
                available.y() + max(0, (available.height() - self.height()) // 2),
            )
        else:
            self.setMinimumSize(360, 520)
            self.setMaximumSize(450, 740)
            self.resize(430, 700)

    def _stylesheet(self):
        return dialog_stylesheet() + f"""
            QDialog {{
                background: transparent;
            }}
            QFrame#LegalSurface {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {GLASS_STRONG_COLOR}, stop:0.54 {PANEL_COLOR}, stop:1 {BG_ELEVATED_COLOR});
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 26px;
            }}
            QLabel#LegalLogo {{
                background: {ACCENT_TINT};
                color: {ACCENT_COLOR};
                border: 1px solid {LINE_COLOR};
                border-radius: 24px;
                font-size: 22px;
                font-weight: 900;
            }}
            QLabel#LegalTitle {{
                color: {TEXT_COLOR};
                font-size: 19px;
                font-weight: 900;
                background: transparent;
            }}
            QLabel#LegalMeta {{
                color: {ACCENT_COLOR};
                font-size: 11px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#LegalIntro {{
                color: {MUTED_TEXT_COLOR};
                font-size: 12px;
                font-weight: 700;
                background: transparent;
            }}
            QTextBrowser#LegalDocument {{
                background: {GLASS_COLOR};
                color: {FIELD_TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 16px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.45;
            }}
            QTextBrowser#LegalDocument viewport {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
            }}
            QCheckBox#LegalConfirmCheck {{
                color: {TEXT_COLOR};
                font-size: 12px;
                font-weight: 800;
                spacing: 10px;
                background: transparent;
            }}
            QPushButton#LegalAgreeButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
                color: {ACCENT_TEXT_COLOR};
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 22px;
                padding: 12px 14px;
                font-size: 14px;
                font-weight: 900;
                min-height: 42px;
            }}
            QPushButton#LegalAgreeButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {BRAND_ACCENT_COLOR}, stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR});
            }}
            QPushButton#LegalAgreeButton:pressed {{
                background: {ACCENT_COLOR};
                padding-top: 15px;
                padding-bottom: 13px;
            }}
            QPushButton#LegalAgreeButton:disabled {{
                background: {PANEL_ELEVATED_COLOR};
                color: {SUBTLE_TEXT_COLOR};
                border-color: {SOFT_LINE_COLOR};
            }}
            QPushButton#LegalDeclineButton {{
                background-color: {ACCENT_TINT};
                color: {TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 20px;
                padding: 11px 12px;
                font-size: 13px;
                font-weight: 800;
                min-height: 40px;
            }}
            QPushButton#LegalDeclineButton:hover {{
                background-color: {HOVER_TINT};
                border-color: {LINE_COLOR};
            }}
            QPushButton#LegalDeclineButton:pressed {{
                background-color: {ACCENT_TINT_STRONG};
            }}
        """
