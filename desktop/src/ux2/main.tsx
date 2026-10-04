// Internal examples only; production has a separate index.html entry.
if (import.meta.env.DEV) {
  void Promise.all([import("react-dom/client"), import("./Gallery")]).then(([{ createRoot }, { Gallery }]) => {
    createRoot(document.getElementById("root")!).render(<Gallery />);
  });
} else document.getElementById("root")!.textContent = "דף הרכיבים זמין בשרת הפיתוח.";
