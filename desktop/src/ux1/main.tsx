// Separate development entry: isolate backend before importing product UI.
if (import.meta.env.DEV) {
  void import("./DemoBackend").then(({ installDemoBackend }) => {
    installDemoBackend();
    return Promise.all([import("react-dom/client"), import("./Prototype")]);
  }).then(([{ createRoot }, { Prototype }]) => {
    createRoot(document.getElementById("root")!).render(<Prototype />);
  });
} else {
  document.getElementById("root")!.textContent = "אב־הטיפוס זמין רק בשרת הפיתוח.";
}
