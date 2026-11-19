"""
Verification Script for Phase 4 - Task T4.1:
Engine selection dropdown placed next to Branch dropdown.
- Fortify (SAST) and Acunetix (DAST) are selectable (enabled).
- Burp Suite and Nessus are dimmed and disabled ("Sắp có").
- Default engine is Fortify.
"""

import sys
import re
from pathlib import Path
from html.parser import HTMLParser

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class HTMLSelectInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_engine_select = False
        self.in_branch_select = False
        self.engine_options = []
        self.branch_options = []
        self.current_tag = None
        self.current_option_attrs = {}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "select":
            if attrs_dict.get("id") == "engine-select":
                self.in_engine_select = True
            elif attrs_dict.get("id") == "branch-select":
                self.in_branch_select = True
        elif tag == "option":
            self.current_tag = "option"
            self.current_option_attrs = attrs_dict

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_engine_select = False
            self.in_branch_select = False
        elif tag == "option":
            self.current_tag = None

    def handle_data(self, data):
        if self.current_tag == "option":
            text = data.strip()
            if text:
                record = {
                    "text": text,
                    "value": self.current_option_attrs.get("value"),
                    "disabled": "disabled" in self.current_option_attrs,
                    "selected": "selected" in self.current_option_attrs,
                    "class": self.current_option_attrs.get("class", "")
                }
                if self.in_engine_select:
                    self.engine_options.append(record)
                elif self.in_branch_select:
                    self.branch_options.append(record)

def test_t41_html_structure():
    print("[1/3] Verifying HTML Structure & Placement...")
    index_path = PROJECT_ROOT / "frontend" / "index.html"
    assert index_path.exists(), f"File {index_path} does not exist"

    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Check both selects exist
    assert 'id="engine-select"' in html_content, "Missing #engine-select in index.html"
    assert 'id="branch-select"' in html_content, "Missing #branch-select in index.html"

    # Check they are co-located in scan-toolbar-card (Engine placed next to Branch)
    toolbar_match = re.search(r'<section class="scan-toolbar-card"[^>]*>([\s\S]*?)<\/section>', html_content)
    assert toolbar_match, "Missing .scan-toolbar-card in index.html"
    toolbar_inner = toolbar_match.group(1)
    assert 'id="engine-select"' in toolbar_inner, "Engine select must be inside toolbar"
    assert 'id="branch-select"' in toolbar_inner, "Branch select must be inside toolbar"

    # Inspect options via HTML parser
    parser = HTMLSelectInspector()
    parser.feed(html_content)

    print(f"  Discovered Engine options: {[o['value'] for o in parser.engine_options]}")
    opts_by_val = {o["value"]: o for o in parser.engine_options}

    # 1. Fortify exists, selectable, and default
    assert "fortify" in opts_by_val, "Fortify option must exist"
    assert not opts_by_val["fortify"]["disabled"], "Fortify must be selectable"
    assert opts_by_val["fortify"]["selected"], "Fortify must be selected by default in HTML"

    # 2. Acunetix exists and selectable
    assert "acunetix" in opts_by_val, "Acunetix option must exist"
    assert not opts_by_val["acunetix"]["disabled"], "Acunetix must be selectable (enabled)"

    # 3. Burp Suite is disabled and labeled 'Sắp có'
    assert "burpsuite" in opts_by_val, "Burp Suite option must exist"
    assert opts_by_val["burpsuite"]["disabled"], "Burp Suite must be disabled"
    assert "sắp có" in opts_by_val["burpsuite"]["text"].lower(), "Burp Suite label must indicate 'Sắp có'"

    # 4. Nessus is disabled and labeled 'Sắp có'
    assert "nessus" in opts_by_val, "Nessus option must exist"
    assert opts_by_val["nessus"]["disabled"], "Nessus must be disabled"
    assert "sắp có" in opts_by_val["nessus"]["text"].lower(), "Nessus label must indicate 'Sắp có'"

    print("  -> PASS: HTML toolbar placement and option attributes verified.")

def test_t41_css_styling():
    print("[2/3] Verifying CSS Styling for Dimmed/Disabled Options...")
    css_path = PROJECT_ROOT / "frontend" / "css" / "style.css"
    assert css_path.exists(), f"File {css_path} does not exist"

    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    assert ".option-coming-soon" in css_content or "option:disabled" in css_content, \
        "CSS must contain styling for dimmed/disabled options"
    assert "not-allowed" in css_content, "CSS should specify cursor: not-allowed for disabled options"

    print("  -> PASS: CSS styling rules for coming-soon options verified.")

def test_t41_js_configuration():
    print("[3/3] Verifying JavaScript SCANNER_ENGINES Configuration & Logic...")
    js_path = PROJECT_ROOT / "frontend" / "js" / "app.js"
    assert js_path.exists(), f"File {js_path} does not exist"

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Verify SCANNER_ENGINES array definition
    assert "SCANNER_ENGINES" in js_content
    assert '"fortify"' in js_content and 'isDefault: true' in js_content
    assert '"acunetix"' in js_content and 'enabled: true' in js_content
    assert '"burpsuite"' in js_content and 'enabled: false' in js_content
    assert '"nessus"' in js_content and 'enabled: false' in js_content

    # Verify default assignment in app logic
    assert 'this.engineSelect.value = "fortify"' in js_content or 'isDefault' in js_content

    print("  -> PASS: JS controller and SCANNER_ENGINES constants verified.")

if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T4.1 (ENGINE SELECTOR)")
    print("=" * 70)
    test_t41_html_structure()
    test_t41_css_styling()
    test_t41_js_configuration()
    print("=" * 70)
    print("ALL TESTS FOR TASK T4.1 PASSED SUCCESSFULLY (100%)")
    print("=" * 70)
