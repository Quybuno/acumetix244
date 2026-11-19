/**
 * Deep Review Frontend - Main Application Controller (Phase 4 - Task T4.1)
 *
 * Implements:
 * - Engine Selection Dropdown next to Branch Dropdown.
 * - Fortify and Acunetix are selectable (enabled).
 * - Burp Suite and Nessus are dimmed and disabled ('Sắp có').
 * - Default engine is 'fortify'.
 */

// Global configuration of scanner engines supported by Deep Review
const SCANNER_ENGINES = [
    {
        id: "fortify",
        label: "Fortify (SAST)",
        description: "Quét tĩnh phân tích lỗ hổng mã nguồn (Source Code Analysis)",
        enabled: true,
        isDefault: true
    },
    {
        id: "acunetix",
        label: "Acunetix (DAST)",
        description: "Quét động ứng dụng Web & API đang chạy (Dynamic Application Security Testing)",
        enabled: true,
        isDefault: false
    },
    {
        id: "burpsuite",
        label: "Burp Suite (Sắp có)",
        description: "Công cụ kiểm thử xâm nhập chuyên sâu (Sắp ra mắt)",
        enabled: false,
        isDefault: false
    },
    {
        id: "nessus",
        label: "Nessus (Sắp có)",
        description: "Quét lỗ hổng hạ tầng mạng và máy chủ (Sắp ra mắt)",
        enabled: false,
        isDefault: false
    }
];

class DeepReviewApp {
    constructor() {
        this.engineSelect = document.getElementById("engine-select");
        this.branchSelect = document.getElementById("branch-select");
        this.scanButton = document.getElementById("btn-scan");
        this.currentProject = "proj-banking";
    }

    /**
     * Initialize application components
     */
    init() {
        this.initEngineSelector();
        this.bindEvents();
    }

    /**
     * Populate and configure the Engine selection dropdown (Task T4.1)
     */
    initEngineSelector() {
        if (!this.engineSelect) return;

        // Clear existing options to ensure deterministic state from configuration
        this.engineSelect.innerHTML = "";

        SCANNER_ENGINES.forEach(engine => {
            const option = document.createElement("option");
            option.value = engine.id;
            option.textContent = engine.label;
            option.disabled = !engine.enabled;

            if (!engine.enabled) {
                option.classList.add("option-coming-soon");
            }

            if (engine.isDefault) {
                option.selected = true;
            }

            this.engineSelect.appendChild(option);
        });

        // Set default value explicitly
        this.engineSelect.value = "fortify";
    }

    bindEvents() {
        if (this.engineSelect) {
            this.engineSelect.addEventListener("change", (e) => {
                this.onEngineChanged(e.target.value);
            });
        }
    }

    onEngineChanged(selectedEngine) {
        // Will be expanded in Task T4.2 (disabling branch on acunetix)
        console.log(`[DeepReview] Engine selected: ${selectedEngine}`);
    }

    /**
     * Get currently selected engine ID
     */
    getSelectedEngine() {
        return this.engineSelect ? this.engineSelect.value : "fortify";
    }
}

// Instantiate on DOMContentLoaded
let appInstance = null;
document.addEventListener("DOMContentLoaded", () => {
    appInstance = new DeepReviewApp();
    appInstance.init();
});

// Export for Node.js / test environments
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        SCANNER_ENGINES,
        DeepReviewApp
    };
}
