/** Shared product copy; profile values and enforcement remain owned by Core. */
export const autonomyProfiles = [
  { value: "locked_down", label: "בטוח", description: "אישור לפני רוב הפעולות", icon: "lock" },
  { value: "balanced", label: "מאוזן", description: "פעולות שוטפות לבד, אישור לפעולות רגישות", icon: "shield" },
  { value: "max_autonomy", label: "אוטונומי", description: "פעולה עצמאית במסגרת המגבלות שהוגדרו", icon: "spark" },
] as const;

export const autonomyLabels: Record<string, string> = {
  ...Object.fromEntries(autonomyProfiles.map(profile => [profile.value, profile.label])),
  custom: "מותאם אישית",
};
