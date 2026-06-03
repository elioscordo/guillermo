let pollingTimer = null;
let pollIteration = 0;
const monitoredObjectIds = new Set();

const updateRowState = (row, status) => {
        // Define which statuses lock the row
        const isLocked = ["0", "1"].includes(status);
        // Find all inputs in the row except the dropdown itself
        const inputs = row.querySelectorAll('input, textarea, select:not(.inline-block select)');
        const saveBtn = row.querySelector('.ajax-save-btn');

        inputs.forEach(input => {
            input.disabled = isLocked;
            input.style.opacity = isLocked ? '0.5' : '1';
        });
        
        if (saveBtn) {
            saveBtn.disabled = isLocked;
            saveBtn.style.pointerEvents = isLocked ? 'none' : 'auto';
        }
    };

const startPolling = () => {
    pollIteration = 0; // Reset counter whenever a new task is added to trigger fast polling
    if (!pollingTimer) {
        pollingTimer = setTimeout(pollStatus, 1000);
    }
};

const pollStatus = () => {
    if (monitoredObjectIds.size === 0) {
        pollingTimer = null;
        console.log("No more objects to monitor.");
        return;
    }
        console.log(`Polling for updates on object IDs: ${Array.from(monitoredObjectIds).join(', ')}`);
        monitoredObjectIds.forEach(objectId => {
            const el = document.getElementById(`task-${objectId}`);
            if (!el) {
                monitoredObjectIds.delete(objectId);
                return;
            }
            const row = el.closest('tr');
        
            fetch(`ajax-last-tasks/${objectId}/`)
                .then(response => response.json())
                .then(data => {
                    // 1. Update the HTML of the dropdown container
                    
                    el.outerHTML = data.html;
                    console.log(`received update for object ID ${objectId}`, data );
                    // Re-fetch the element as the reference 'el' is now detached from the DOM`
                    const updatedEl = document.getElementById(`task-${objectId}`);
                    if (updatedEl) {
                        updatedEl.setAttribute('data-status', String(data.status));
                    }

                    // Remove from monitoring if terminal status reached (specifically 4 as requested)
                    // We also check for any status that isn't pending (0 or 1) to avoid infinite polling on errors
                    if (data.status == "4" || (data.status != "0" && data.status != "1")) {
                        monitoredObjectIds.delete(objectId);
                    }
                    
                    // 2. If task succeeded, update row content with serialized data
                    if (data.object) {
                        // Update editable inputs in the row
                        Object.keys(data.object).forEach(key => {
                            const input = row.querySelector(`[name$="-${key}"]`);
                            if (input && input.value !== String(data.object[key])) {
                                input.value = data.object[key];
                            }
                        });
                    }

                    if (data.refresh) {
                        Object.keys(data.refresh).forEach(key => {
                            const fieldEl = row.querySelector(`.field-${key}`);
                            console.log(`Refreshing field '${key}' with new content.`);
                            if (fieldEl) {
                                fieldEl.innerHTML = data.refresh[key];
                            }
                        });
                    }

                    
                    // 3. Toggle row inputs based on new status
                    updateRowState(row, String(data.status));
                });
        });

        // Calculate next delay: 1s for the first 3 polls, then 5s
        const delay = pollIteration < 3 ? 1000 : 5000;
        pollIteration++;
        pollingTimer = setTimeout(pollStatus, delay);
    };

const logShiftFields = () => {
    const list = window.ajaxShiftFields || [];
    console.log(`%c[AdminAjax] Configured Shift+Enter fields: ${JSON.stringify(list)}`, "color: #3b82f6; font-weight: bold;");
};

document.addEventListener('keydown', function(e) {
    if (e.target.name && e.target.name.startsWith('form-')) {
        const input = e.target;
        const cleanName = input.name.split('-').slice(-1)[0];
        const shiftFields = window.ajaxShiftFields || [];
        const isShiftField = shiftFields.includes(cleanName);

        // Debug log to verify field detection
        console.log(`[AdminAjax] Keydown on: ${cleanName} | isShiftField: ${isShiftField} | Key: ${e.key} | Shift: ${e.shiftKey}`);
        
        const shouldTrigger = isShiftField ? (e.key === 'Enter' && e.shiftKey) : (e.key === 'Enter' && !e.shiftKey);

        if (shouldTrigger) {
            e.preventDefault();
            const row = input.closest('tr');
            const idInput = row.querySelector('input.action-select');
            if (!idInput) return;
            const objectId = idInput.value;
            updateRowState(row, "0"); // Optimistically lock the row immediately
            // Extract the clean field name (e.g., "notes")
            const cleanName = input.name.split('-').slice(-1)[0];
            const value = input.type === 'checkbox' ? (input.checked ? 'on' : '') : input.value;

            const formData = new URLSearchParams();
            formData.append(cleanName, value);
            formData.append('single_field_mode', cleanName); // Tell Django which field we're updating

            fetch(`ajax-update/${objectId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            })
            .then(response => {
                if (response.ok) {
                    const dropdowns = row.querySelector('.inline-block[id^="task-"]');
                    dropdowns.setAttribute('data-status', '1');
                    monitoredObjectIds.add(objectId);
                    startPolling();
                }
            });
        }
    }
});

// Handle Prompt Preview Presets
document.addEventListener('change', function(e) {
    if (e.target.classList.contains('prompt-preset-select')) {
        const select = e.target;
        const preset = select.value;
        const url = select.getAttribute('data-url');
        const container = select.closest('.prompt-preview-container');
        const contentArea = container.querySelector('.prompt-preview-content');

        contentArea.textContent = "Loading preview...";

        fetch(`${url}?preset=${preset}`)
            .then(response => response.json())
            .then(data => {
                contentArea.textContent = data.content || "No content generated for this preset.";
            })
            .catch(err => {
                contentArea.textContent = "Error loading prompt preview.";
            });
    }
});

// Fetch configuration from the server
const fetchConfig = () => {
    return fetch('ajax-config/')
        .then(response => {
            if (!response.ok) throw new Error("Config fetch failed");
            return response.json();
        })
        .then(data => {
            window.ajaxShiftFields = data.ajax_shift_fields || [];
            logShiftFields();
        })
        .catch(err => console.error("[AdminAjax] Could not load config:", err));
};

// Initialize monitoring for any tasks already in progress on page load
const initTaskMonitoring = () => {
    fetchConfig();
    document.querySelectorAll('[id^="task-"]').forEach(el => {
        const status = el.getAttribute('data-status');
        if (["0", "1"].includes(status)) {
            const objectId = el.id.replace('task-', '');
            monitoredObjectIds.add(objectId);
            
            const row = el.closest('tr');
            if (row) {
                updateRowState(row, status);
            }
        }
    });
    if (monitoredObjectIds.size > 0) {
        startPolling();
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTaskMonitoring);
} else {
    initTaskMonitoring();
}
