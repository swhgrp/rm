# SW Hospitality Group - Design & Styling Standards
**Template System:** Accounting System (base.html)
**Last Updated:** 2025-10-30

## Purpose
This document defines the standardized design system for all microservices in the SW Hospitality Group Restaurant Management System. All systems should follow these standards for consistency.

---

## 1. SIDEBAR STRUCTURE (Standard Format)

### Sidebar Brand Section
```html
<div class="sidebar-brand">
    <img src="/SYSTEM/static/images/sw-logo.png" alt="SW Logo">
</div>
```

**Rules:**
- ✅ **Use company logo** (SW HOSPITALITY GROUP)
- ✅ Logo max-width: 180px
- ✅ Centered alignment
- ✅ Bottom border: 1px solid #30363d
- ❌ Do NOT use system name in sidebar header
- ❌ Do NOT use emoji icons

**Rationale:** Logo provides consistent branding. System name goes in the main page header.

---

## 2. PAGE HEADER STRUCTURE (Standard Format)

### Main Header with Icon
```html
<div class="top-header">
    <h1>
        <i class="bi bi-ICON-NAME"></i> System Name
    </h1>
    <div class="user-info">
        <i class="bi bi-person-circle"></i>
        <span>{{ current_user.full_name }}</span>
    </div>
</div>
```

### Dashboard Title
```html
<h2 class="mb-0">
    <i class="bi bi-speedometer2"></i> System Dashboard
</h2>
<p class="text-muted">Brief description of the dashboard</p>
```

**Standard Format:**
- Use `<h2>` tag (not h1)
- Include system name: "Inventory Dashboard", "Financial Dashboard", etc.
- Add `mb-0` class to remove bottom margin
- Use system-appropriate icon before title

**Bootstrap Icons by System:**
- **Accounting:** `bi-calculator`
- **Inventory:** `bi-box-seam`
- **HR:** `bi-people`
- **Events:** `bi-calendar-event`
- **Integration Hub:** `bi-diagram-3`
- **Files:** `bi-folder2`
- **Portal:** `bi-grid` or `bi-house-door`

---

## 3. COLOR PALETTE (Standard)

### Base Colors
```css
--bg-primary: #0d1117;        /* Main background */
--bg-secondary: #161b22;      /* Sidebar, cards */
--bg-tertiary: #21262d;       /* Hover states */
--border-color: #30363d;      /* Borders */
```

### Text Colors
```css
--text-primary: #c9d1d9;      /* Main text */
--text-secondary: #8b949e;    /* Muted/secondary text */
--text-accent: #58a6ff;       /* Links, active states */
```

### Semantic Colors
```css
--color-success: #238636;     /* Green - buttons, success */
--color-success-hover: #2ea043;
--color-danger: #da3633;      /* Red - errors, delete */
--color-warning: #9e6a03;     /* Orange - warnings */
--color-info: #1f6feb;        /* Blue - info messages */
```

---

## 4. TYPOGRAPHY STANDARDS

### Font Family
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
```

### Font Sizes
```css
/* Sidebar */
--sidebar-brand: 16px;
--sidebar-nav: 14px;
--sidebar-icon: 16px;

/* Top Navbar */
--page-title: 18px (in navbar);

/* Page Content Headers */
h2: 1.75rem (~28px) - Dashboard titles
h3: 1.5rem (~24px) - Section headers
--page-subtitle: 14px;

/* Content */
--body-text: 14px;
--small-text: 12px;
--card-title: 18px;
```

### Font Weights
```css
--weight-normal: 400;
--weight-medium: 500;
--weight-semibold: 600;
--weight-bold: 700;
```

---

## 5. SIDEBAR NAVIGATION STANDARDS

### Fixed Elements (All Systems)
```html
<ul class="sidebar-nav">
    <!-- Always first -->
    <li><a href="/"><i class="bi bi-house-door"></i> Portal Home</a></li>
    <li><a href="/SYSTEM/"><i class="bi bi-speedometer2"></i> Dashboard</a></li>

    <!-- System-specific sections below -->
</ul>
```

### Collapsible Sections
```html
<li>
    <a href="#" class="nav-section-toggle" onclick="toggleSection('sectionId', event); return false;">
        <i class="bi bi-ICON"></i> Section Name
        <i class="bi bi-chevron-down float-end"></i>
    </a>
    <ul id="sectionId" class="submenu">
        <li><a href="page1"><i class="bi bi-ICON"></i> Sub Item 1</a></li>
        <li><a href="page2"><i class="bi bi-ICON"></i> Sub Item 2</a></li>
    </ul>
</li>
```

### Active State Highlighting
```html
<!-- In page template -->
{% block nav_page_name %}active{% endblock %}

<!-- In base.html -->
<a href="page" class="{% block nav_page_name %}{% endblock %}">...</a>
```

---

## 6. SIDEBAR DIMENSIONS

```css
.sidebar {
    width: 200px;           /* Fixed width */
    height: 100vh;          /* Full height */
    position: fixed;
    top: 0;
    left: 0;
    background: #161b22;
    border-right: 1px solid #30363d;
    z-index: 1000;
}

.main-content {
    margin-left: 200px;     /* Match sidebar width */
    padding: 20px;
}
```

### Mobile Responsive
```css
@media (max-width: 768px) {
    .sidebar {
        transform: translateX(-200px);  /* Hidden by default */
    }

    .sidebar.show {
        transform: translateX(0);        /* Slide in */
    }

    .main-content {
        margin-left: 0;                  /* Full width */
    }
}
```

---

## 7. CARD COMPONENTS

### Standard Card
```html
<div class="card">
    <div class="card-header">
        <h5><i class="bi bi-ICON"></i> Card Title</h5>
    </div>
    <div class="card-body">
        <!-- Content -->
    </div>
</div>
```

### Card Styling
```css
.card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    margin-bottom: 20px;
}

.card-header {
    background-color: #21262d;
    border-bottom: 1px solid #30363d;
    padding: 15px 20px;
}
```

---

## 8. BUTTON STANDARDS

### Primary Button (Success)
```html
<button class="btn btn-success">
    <i class="bi bi-plus-circle"></i> Action
</button>
```

### Secondary Button
```html
<button class="btn btn-secondary">
    <i class="bi bi-x-circle"></i> Cancel
</button>
```

### Danger Button
```html
<button class="btn btn-danger">
    <i class="bi bi-trash"></i> Delete
</button>
```

### Button Sizes
```css
.btn {
    padding: 8px 16px;      /* Standard */
    font-size: 14px;
}

.btn-sm {
    padding: 6px 12px;      /* Small */
    font-size: 12px;
}

.btn-lg {
    padding: 12px 24px;     /* Large */
    font-size: 16px;
}
```

---

## 9. FORM STANDARDS

### Form Group
```html
<div class="form-group mb-3">
    <label for="inputId" class="form-label">Label Text</label>
    <input type="text" class="form-control" id="inputId" name="name">
    <small class="form-text">Helper text</small>
</div>
```

### Input Styling
```css
.form-control {
    background-color: #0d1117;
    border: 1px solid #30363d;
    color: #c9d1d9;
    border-radius: 6px;
    padding: 8px 12px;
}

.form-control:focus {
    border-color: #58a6ff;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
    background-color: #0d1117;
    color: #c9d1d9;
}
```

---

## 10. TABLE STANDARDS

### Standard Table
```html
<div class="table-responsive">
    <table class="table table-hover">
        <thead>
            <tr>
                <th>Column 1</th>
                <th>Column 2</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Data 1</td>
                <td>Data 2</td>
                <td>
                    <button class="btn btn-sm btn-primary">
                        <i class="bi bi-pencil"></i>
                    </button>
                </td>
            </tr>
        </tbody>
    </table>
</div>
```

### Table Styling
```css
.table {
    color: #c9d1d9;
    border-color: #30363d;
}

.table thead {
    background-color: #161b22;
    border-bottom: 2px solid #30363d;
}

.table tbody tr:hover {
    background-color: #21262d;
}
```

---

## 11. ICON USAGE

### Icon Library
**Use:** Bootstrap Icons (CDN)
```html
<link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.10.0/font/bootstrap-icons.min.css" rel="stylesheet">
```

### Common Icons
- Navigation: `bi-house-door`, `bi-speedometer2`
- Actions: `bi-plus-circle`, `bi-pencil`, `bi-trash`, `bi-eye`
- Status: `bi-check-circle`, `bi-x-circle`, `bi-clock`
- Data: `bi-file-earmark`, `bi-folder`, `bi-download`
- User: `bi-person-circle`, `bi-people`

### Icon Sizing
```css
.sidebar-nav i { font-size: 16px; }  /* Sidebar */
.btn i { font-size: 14px; }          /* Buttons */
.page-header i { font-size: 24px; }  /* Headers */
```

---

## 12. RESPONSIVE BREAKPOINTS

```css
/* Mobile First */
@media (max-width: 480px) {
    /* Phone portrait */
}

@media (max-width: 768px) {
    /* Tablet portrait, phone landscape */
}

@media (max-width: 992px) {
    /* Tablet landscape, small desktop */
}

@media (min-width: 1200px) {
    /* Large desktop */
}
```

---

## 13. SPACING SYSTEM

### Padding/Margin Scale
```css
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;
```

### Common Spacing
```css
.card { padding: 20px; }
.section-spacing { margin-bottom: 30px; }
.content-padding { padding: 20px 30px; }
```

---

## 14. IMPLEMENTATION CHECKLIST

When updating a system to match standards:

- [ ] Copy `base.html` from Accounting system
- [ ] Update `<base href="/SYSTEM/">` tag
- [ ] Replace logo path: `/SYSTEM/static/images/sw-logo.png`
- [ ] Update sidebar navigation sections
- [ ] Update page title: "System Name - Accounting/Inventory/etc"
- [ ] Replace all emoji icons with Bootstrap Icons
- [ ] Ensure "Portal Home" is first nav item
- [ ] Add collapsible sections with chevron icons
- [ ] Update main page headers with system icon
- [ ] Test mobile responsiveness
- [ ] Verify dark theme colors throughout
- [ ] Check all form elements have proper styling
- [ ] Validate button styles and sizes
- [ ] Test all nav links and active states

---

## 15. SYSTEM-SPECIFIC CUSTOMIZATIONS

### Per-System Variables
Each system should define these in their base.html:

```css
/* Update per system */
--system-primary-color: #238636;   /* Can customize per system */
--system-name: "Accounting";        /* For titles */
--system-icon: "bi-calculator";     /* Main icon */
```

### Allowed Customizations
- Dashboard layout and widgets
- Report-specific visualizations
- System-specific feature UI
- Chart colors (maintain contrast)

### NOT Allowed
- Sidebar structure changes
- Base color palette modifications
- Typography changes
- Button/form styling changes
- Navigation patterns

---

## 16. QUALITY ASSURANCE

### Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Accessibility
- WCAG 2.1 Level AA compliant
- Keyboard navigation support
- Screen reader compatible
- Minimum contrast ratio 4.5:1

### Performance
- CSS embedded in base.html (no external CSS files)
- CDN for Bootstrap and icons
- Minimal JavaScript dependencies
- Mobile-optimized

---

## REFERENCE IMPLEMENTATION

**Master Template:** `/opt/restaurant-system/accounting/src/accounting/templates/base.html`

All systems should use Accounting's base.html as the starting point and customize only the navigation sections and system-specific content.

---

## IMPLEMENTATION STATUS

**Last Updated:** 2025-10-30

### ✅ Fully Standardized Systems

| System | Status | Sidebar | Top Navbar | Dashboard Title | Font Sizes | Layout |
|--------|--------|---------|------------|-----------------|------------|--------|
| **Accounting** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **Inventory** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **HR** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **Events** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **Integration Hub** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **Files** | ✅ Complete | Logo only | System name + icon | h2, 1.75rem | 14px nav | Fixed sidebar |
| **Portal** | ✅ Complete | Logo only | System name + icon | N/A (dashboard) | N/A | Card-based |

### Key Changes Implemented (2025-10-30)

1. **Inventory System**: Updated navbar, dashboard title, added h2 styling
2. **HR System**: Replaced dynamic page title with fixed system name, standardized dashboard
3. **Events System**: Updated navbar, simplified dashboard, added logo in sidebar, updated CSS
4. **Integration Hub**: Standardized dashboard title format, added h2 styling
5. **Files System**: Complete layout restructure - moved from full-width navbar to fixed sidebar layout
6. **All Systems**: Consistent 14px font-size for sidebar navigation links

### Design Consistency Achieved

- ✅ All sidebars display SW Hospitality Group logo only (no system names)
- ✅ All top navbars display system name with Bootstrap icon
- ✅ All dashboard titles use h2 tag with 1.75rem font size
- ✅ All sidebar navigation links use 14px font size
- ✅ All systems use fixed sidebar (200px width) with main wrapper layout
- ✅ All systems follow GitHub dark theme color palette
- ✅ Consistent hover effects with left border highlight (#58a6ff)

### Total Systems: 7/7 Standardized (100% Complete)
