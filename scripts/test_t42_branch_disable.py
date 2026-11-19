"""
Verification Script for Phase 4 - Task T4.2:
Branch dropdown is disabled when Acunetix is selected, accompanied by the explanation:
"Acunetix quét ứng dụng đang chạy qua URL, không đọc mã nguồn trong Git"
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_EXPLANATION = "Acunetix quét ứng dụng đang chạy qua URL, không đọc mã nguồn trong Git"


def test_t42_static_assets():
    print("[1/2] Verifying HTML & CSS for Branch Disabling & Explanation...")
    html_path = PROJECT_ROOT / "frontend" / "index.html"
    css_path = PROJECT_ROOT / "frontend" / "css" / "style.css"
    js_path = PROJECT_ROOT / "frontend" / "js" / "app.js"

    html_content = html_path.read_text(encoding="utf-8")
    css_content = css_path.read_text(encoding="utf-8")
    js_content = js_path.read_text(encoding="utf-8")

    assert 'id="branch-select"' in html_content, "Missing #branch-select"
    assert 'id="branch-explanation"' in html_content, "Missing #branch-explanation"
    assert ".form-select:disabled" in css_content, "Missing .form-select:disabled CSS rule"
    assert ".branch-disabled-note" in css_content, "Missing .branch-disabled-note CSS rule"
    assert EXPECTED_EXPLANATION in js_content, f"Missing exact explanation text: {EXPECTED_EXPLANATION}"

    print("  -> PASS: Static HTML, CSS, and JS constants verified.")


def test_t42_js_runtime_behavior():
    print("[2/2] Running Node.js DOM Simulation for Engine Switching...")
    app_js_path = (PROJECT_ROOT / "frontend" / "js" / "app.js").as_posix()

    node_script = f"""
    const assert = require('assert');

    function createMockClassList() {{
        const set = new Set();
        return {{
            add: (c) => set.add(c),
            remove: (c) => set.delete(c),
            contains: (c) => set.has(c)
        }};
    }}

    function createMockElement(id) {{
        return {{
            id,
            value: '',
            disabled: false,
            textContent: '',
            innerHTML: '',
            children: [],
            attributes: {{}},
            classList: createMockClassList(),
            listeners: {{}},
            appendChild(child) {{ this.children.push(child); }},
            setAttribute(k, v) {{ this.attributes[k] = v; }},
            removeAttribute(k) {{ delete this.attributes[k]; }},
            addEventListener(ev, fn) {{ this.listeners[ev] = fn; }},
            dispatchChange(newVal) {{
                this.value = newVal;
                if (this.listeners['change']) {{
                    this.listeners['change']({{ target: {{ value: newVal }} }});
                }}
            }}
        }};
    }}

    const elements = {{
        'engine-select': createMockElement('engine-select'),
        'branch-select': createMockElement('branch-select'),
        'branch-explanation': createMockElement('branch-explanation'),
        'btn-scan': createMockElement('btn-scan')
    }};

    global.document = {{
        getElementById: (id) => elements[id] || null,
        createElement: (tag) => ({{
            tagName: tag,
            value: '',
            textContent: '',
            disabled: false,
            selected: false,
            classList: createMockClassList()
        }}),
        addEventListener: () => {{}}
    }};

    const {{ DeepReviewApp, BRANCH_EXPLANATIONS }} = require('{app_js_path}');
    const app = new DeepReviewApp();
    app.init();

    // 1. Default state: Fortify selected -> Branch is enabled
    assert.strictEqual(elements['engine-select'].value, 'fortify');
    assert.strictEqual(elements['branch-select'].disabled, false);
    assert.strictEqual(elements['branch-explanation'].textContent, BRANCH_EXPLANATIONS.fortify);
    assert.strictEqual(elements['branch-explanation'].classList.contains('branch-disabled-note'), false);

    // 2. Switch to Acunetix -> Branch must be disabled with exact explanation
    elements['engine-select'].dispatchChange('acunetix');
    assert.strictEqual(elements['branch-select'].disabled, true, 'Branch must be disabled for Acunetix');
    assert.strictEqual(elements['branch-select'].attributes['aria-disabled'], 'true');
    assert.strictEqual(
        elements['branch-explanation'].textContent,
        '{EXPECTED_EXPLANATION}'
    );
    assert.strictEqual(elements['branch-explanation'].classList.contains('branch-disabled-note'), true);

    // 3. Switch back to Fortify -> Branch must be re-enabled
    elements['engine-select'].dispatchChange('fortify');
    assert.strictEqual(elements['branch-select'].disabled, false, 'Branch must be re-enabled for Fortify');
    assert.strictEqual(elements['branch-select'].attributes['aria-disabled'], undefined);
    assert.strictEqual(elements['branch-explanation'].textContent, BRANCH_EXPLANATIONS.fortify);
    assert.strictEqual(elements['branch-explanation'].classList.contains('branch-disabled-note'), false);

    console.log('NODE_DOM_SIMULATION_OK');
    """

    proc = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    if proc.returncode != 0:
        print("Node stdout:", proc.stdout)
        print("Node stderr:", proc.stderr)
        sys.exit(1)

    assert "NODE_DOM_SIMULATION_OK" in proc.stdout
    print("  -> PASS: Runtime engine-switching DOM behavior verified via Node.js.")


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T4.2 (BRANCH DISABLE ON ACUNETIX)")
    print("=" * 70)
    test_t42_static_assets()
    test_t42_js_runtime_behavior()
    print("=" * 70)
    print("ALL TESTS FOR TASK T4.2 PASSED SUCCESSFULLY (100%)")
    print("=" * 70)
