import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { Alert, Badge, Button, Dialog, EmptyState, Field, IconButton, Menu, Resizer, Skeleton, Tabs, Textarea } from "./ui";

describe("accessible base components", () => {
  test("renders controls with semantic labels and roles", () => {
    const html = renderToStaticMarkup(<><Button variant="primary">שמירה</Button><IconButton label="סגירה">×</IconButton><Field aria-label="שם" /><Textarea aria-label="תיאור" /><Menu label="פעולות"><button role="menuitem">עריכה</button></Menu><Tabs label="עמודים" tabs={[{ id: "one", label: "ראשי" }]} active="one" onSelect={() => undefined} /><Resizer label="שינוי רוחב" /></>);
    expect(html).toContain('aria-label="סגירה"'); expect(html).toContain('role="menu"'); expect(html).toContain('role="tablist"'); expect(html).toContain('role="separator"');
  });

  test("renders feedback, loading, empty, and modal primitives", () => {
    const html = renderToStaticMarkup(<><Badge tone="success">מחובר</Badge><Alert tone="warning" title="שימו לב">פרטים</Alert><Skeleton width="60%" /><EmptyState icon="◇" title="ריק" description="אין תוכן" /><Dialog title="אישור" onClose={() => undefined}>תוכן</Dialog></>);
    expect(html).toContain('role="status"'); expect(html).toContain('aria-modal="true"'); expect(html).toContain("ui-skeleton"); expect(html).toContain("אין תוכן");
  });
});
