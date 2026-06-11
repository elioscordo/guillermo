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

                    applyRefreshData(row, data.refresh);

                    
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
            updateRowState(row, "0");

            const targetField = input.name.split('-').slice(-1)[0];
            const formData = new URLSearchParams();

            row.querySelectorAll('input, textarea, select').forEach(el => {
                if (el.name && !el.classList.contains('action-select')) {
                    const fieldName = el.name.split('-').slice(-1)[0];
                    const val = el.type === 'checkbox' ? (el.checked ? 'on' : '') : el.value;
                    formData.set(fieldName, val);
                }
            });
            formData.append('target_field', targetField);

            fetch(`ajax-update/${objectId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            })
            .then(response => {
                return response.json();
            })
            .then(data => {
                if (data.status === "success") {
                    // Immediate UI update from the direct response
                    applyRefreshData(row, data.refresh);
                    
                    const dropdowns = row.querySelector('.inline-block[id^="task-"]');
                    if (dropdowns) {
                        dropdowns.setAttribute('data-status', '1');
                        monitoredObjectIds.add(objectId);
                        startPolling();
                    }
                }
            });
        }
    }
});

const applyRefreshData = (container, refreshData) => {
    if (!refreshData) return;
    Object.keys(refreshData).forEach(key => {
        const fieldEl = container.querySelector(`.field-${key}`);
        if (fieldEl) {
            console.log(`[AdminAjax] Refreshing field '${key}' content`);
            fieldEl.innerHTML = refreshData[key];
        }
    });
    addInputHints();
};

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

// Image Dropdown Menu Logic
document.addEventListener('click', function(e) {
    const container = e.target.closest('.image-menu-container');
    const existingMenu = document.querySelector('.image-dropdown-menu');

    // Close existing menu if clicking outside
    if (existingMenu && !existingMenu.contains(e.target)) {
        existingMenu.remove();
    }

    // Allow the menu to trigger on both actual images and our new placeholders
    const isImageTrigger = e.target.tagName === 'IMG' || e.target.closest('.image-placeholder');

    if (!container || !isImageTrigger) {
        document.querySelectorAll('.image-dropdown-menu').forEach(m => m.remove());
        return;
    }

    e.preventDefault();
    e.stopPropagation();

    document.querySelectorAll('.image-dropdown-menu').forEach(m => m.remove());

    const menu = document.createElement('div');
    // Appending to body and using absolute positioning to avoid clipping by table row overflow
    menu.className = 'image-dropdown-menu absolute z-[999] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-xl py-1 text-xs min-w-[160px] overflow-hidden';
    
    const rect = e.target.getBoundingClientRect();
    menu.style.top = (rect.top + window.scrollY) + 'px';
    menu.style.left = (rect.left + window.scrollX) + 'px';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 transition-colors';
    copyBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">content_copy</span> <span>Copy URL</span>';
    copyBtn.onclick = (ev) => {
        ev.stopPropagation();
        navigator.clipboard.writeText(container.dataset.url).then(() => {
            const span = copyBtn.querySelector('span:last-child');
            span.textContent = "Copied!";
            setTimeout(() => menu.remove(), 800);
        });
    };

    const pasteBtn = document.createElement('button');
    pasteBtn.className = 'w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 transition-colors';
    pasteBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">content_paste</span> <span>Paste URL</span>';
    pasteBtn.onclick = (ev) => {
        ev.stopPropagation();

        const handleUrl = (url) => {
            const trimmed = url ? url.trim() : "";
            if (trimmed && (trimmed.match(/^https?:\/\/.+/i) || trimmed.startsWith('/media/'))) {
                updateImageField(container, trimmed);
            } else if (url) {
                console.warn("[AdminAjax] Invalid URL format - must start with http/https or /media/");
                alert("Invalid URL format. It must start with http://, https:// or /media/");
            }
            menu.remove();
        };

        const showPromptFallback = (defaultVal = "") => {
            const newUrl = prompt("Enter Image URL to replace this item:", defaultVal);
            console.log("[AdminAjax] URL entered via prompt:", newUrl);
            handleUrl(newUrl);
        };

        if (navigator.clipboard && navigator.clipboard.readText) {
            navigator.clipboard.readText().then(clipText => {
                const text = clipText ? clipText.trim() : "";
                // If it looks like a valid external URL, auto-paste it.
                // If it contains /media/ or isn't a URL, trigger the manual prompt.
                if (text.match(/^https?:\/\/.+/i) && !text.includes('/media/')) {
                    console.log("[AdminAjax] Auto-pasting URL from clipboard:", text);
                    handleUrl(text);
                } else {
                    showPromptFallback(text.includes('/media/') ? '' : text);
                }
            }).catch(() => showPromptFallback());
        } else {
            showPromptFallback();
        }
    };

    menu.appendChild(copyBtn);
    menu.appendChild(pasteBtn);
    document.body.appendChild(menu);
});

function updateImageField(container, url) {
    console.log("[AdminAjax] updateImageField triggered:", {
        model: container.dataset.model,
        id: container.dataset.id,
        field: container.dataset.field,
        url: url
    });

    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!csrfInput) {
        console.error("[AdminAjax] CSRF token not found in page.");
        alert("Error: CSRF token missing.");
        return;
    }

    const formData = new FormData();
    formData.append('_model_label', container.dataset.model);
    formData.append('_id', container.dataset.id);
    formData.append('_field', container.dataset.field);
    formData.append('_value', url);

    const endpoint = window.location.pathname.split('/').slice(0, 4).join('/') + '/ajax-section-update/';
    console.log("[AdminAjax] Target endpoint:", endpoint);
    
    fetch(endpoint, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfInput.value,
        },
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            console.log("[AdminAjax] Image update successful");
            const row = container.closest('tr');
            if (row && data.refresh) {
                applyRefreshData(row, data.refresh);
            } else if (data.refresh && data.refresh[container.dataset.field]) {
                container.outerHTML = data.refresh[container.dataset.field];
            } else {
                location.reload(); 
            }
        } else {
            alert("Error: " + (data.error || "Failed to update image"));
            console.log(data.error)
        }
    })
    .catch(err => alert("Communication error: " + err));
}

const addInputHints = () => {
    const shiftFields = window.ajaxShiftFields || [];
    document.querySelectorAll('textarea[name^="form-"], input[name^="form-"][type="text"]').forEach(input => {
        const fieldName = input.name.split('-').pop();
        if (input.nextElementSibling?.classList.contains('ajax-help-text')) return;

        const isShift = shiftFields.includes(fieldName);
        const hint = document.createElement('div');
        hint.className = 'ajax-help-text';
        hint.textContent = isShift ? "⚡ Shift + Enter to save" : "⏎ Enter to save";
        input.after(hint);
    });
};

/**
 * Refreshes a specific collapsible section (Characters, Props, Renders, etc.)
 */
window.refreshSection = (objectId, sectionKey) => {
    const container = document.getElementById(`section-content-${sectionKey}-${objectId}`);
    if (!container) {
        console.warn(`[AdminAjax] Container not found for section: ${sectionKey} (ID: ${objectId})`);
        return;
    }

    container.classList.add('opacity-40', 'pointer-events-none');
    
    // Construct URL based on current admin path (works for /admin/scene/story/ or /admin/scene/scene/)
    const baseUrl = window.location.pathname.split('/').slice(0, 4).join('/');
    const url = `${baseUrl}/refresh-section/${objectId}/${sectionKey}/`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.html) {
                container.innerHTML = data.html;
            }
        })
        .catch(error => console.error(`[AdminAjax] Error refreshing section ${sectionKey}:`, error))
        .finally(() => {
            container.classList.remove('opacity-40', 'pointer-events-none');
        });
};

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
            addInputHints();
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
