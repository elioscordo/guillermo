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
                    el.innerHTML = data.html;
                    el.setAttribute('data-status', String(data.status));

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

                    
                    // 3. Toggle row inputs based on new status
                    updateRowState(row, String(data.status));
                });
        });

        // Calculate next delay: 1s for the first 3 polls, then 5s
        const delay = pollIteration < 3 ? 1000 : 5000;
        pollIteration++;
        pollingTimer = setTimeout(pollStatus, delay);
    };


document.addEventListener('keydown', function(e) {
    if (e.target.name && e.target.name.startsWith('form-')) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const input = e.target;
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
