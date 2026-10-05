// Short product copy; the Core's tool schemas and execution contracts stay authoritative.
export const builtinToolDescriptions: Record<string, string> = {
  get_tool_info: "מציג את יכולות הכלי, הפעולות והפרטים הנדרשים לשימוש בו.",
  search_tools: "מאתר כלים ומיומנויות זמינים לפי הפעולה שברצונך לבצע.",
  system_manager: "מריץ פקודות ובדיקות פרויקט, מציג תהליכים ומנהל את הלוח ועוצמת הקול.",
  software_manager: "מאתר ופותח תוכנות מותקנות במחשב ומרענן את רשימתן.",
  file_manager: "קורא, מחפש ומנהל קבצים ותיקיות, כולל השוואה, כיווץ והעברה לסל המחזור.",
  web_manager: "מחפש מידע ברשת, קורא אתרים ומציג תחזית מזג אוויר.",
  screen_manager: "מצלם את המסך, שומר צילומי מסך ומנתח תמונות.",
  background_task_manager: "מתזמן משימות ברקע, מציג את מצבן ומאפשר ביטול או ניסיון חוזר.",
  notification_manager: "מציג התראות במחשב ומנהל תזכורות ואירועים ביומן.",
  memory_manager: "מחפש בזיכרון המקומי ומנהל את ייבואו וייצואו.",
  canvas_manager: "יוצר ומעדכן תוצרים חזותיים ואינטראקטיביים, כגון תרשימים וטבלאות.",
  email_manager: "מחפש וקורא דואר, מכין ושולח הודעות ומנהל תיקיות וקבצים מצורפים.",
  browser_automation_manager: "מפעיל אתרים בדפדפן: ניווט, מילוי טפסים, העלאה והורדה של קבצים וצילום דפים.",
  computer_automation_manager: "מזהה ומפעיל כפתורים, שדות וחלונות בתוכנות Windows.",
  document_manager: "יוצר ועורך מסמכי Word, משווה מסמכים וממיר אותם לקבצים אחרים.",
  extension_manager: "מאתר, מתקין ומפעיל חיבורים ומיומנויות להרחבת היכולות.",
  create_python_tool: "יוצר כלים מותאמים למשימה באמצעות קוד Python.",
};

export function builtinToolDescription(name: string) {
  return builtinToolDescriptions[name] || "כלי מובנה לביצוע פעולות מתוך השיחה.";
}
