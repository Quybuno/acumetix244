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

// Explanation texts for Branch field depending on selected engine (Task T4.2)
const BRANCH_EXPLANATIONS = {
    fortify: "Nhánh Git chứa mã nguồn để quét SAST",
    acunetix: "Acunetix quét ứng dụng đang chạy qua URL, không đọc mã nguồn trong Git"
};

class DeepReviewApp {
    constructor() {
        this.engineSelect = document.getElementById("engine-select");
        this.branchSelect = document.getElementById("branch-select");
        this.branchExplanation = document.getElementById("branch-explanation");
        this.scanButton = document.getElementById("btn-scan");
        this.currentProject = "proj-banking";
    }

    /**
     * Initialize application components
     */
    init() {
        this.initEngineSelector();
        this.bindEvents();
        this.updateBranchState(this.getSelectedEngine());
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
        this.updateBranchState(selectedEngine);
    }

    /**
     * Disable Branch dropdown and show explanation when Acunetix is selected (Task T4.2)
     */
    updateBranchState(engineId) {
        if (!this.branchSelect) return;

        const isAcunetix = engineId === "acunetix";
        this.branchSelect.disabled = isAcunetix;

        if (isAcunetix) {
            this.branchSelect.setAttribute("aria-disabled", "true");
            if (this.branchExplanation) {
                this.branchExplanation.textContent = BRANCH_EXPLANATIONS.acunetix;
                this.branchExplanation.classList.add("branch-disabled-note");
            }
        } else {
            this.branchSelect.removeAttribute("aria-disabled");
            if (this.branchExplanation) {
                this.branchExplanation.textContent = BRANCH_EXPLANATIONS.fortify;
                this.branchExplanation.classList.remove("branch-disabled-note");
            }
        }
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
if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => {
        appInstance = new DeepReviewApp();
        appInstance.init();
    });
}

// Export for Node.js / test environments
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        SCANNER_ENGINES,
        BRANCH_EXPLANATIONS,
        DeepReviewApp
    };
}
