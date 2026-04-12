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
const pollStatus = () => {
        const dropdowns = document.querySelectorAll('.inline-block[id^="task-"]');
        
        dropdowns.forEach(el => {
            const objectId = el.id.split('-')[1];
            const status = el.getAttribute('data-status');
            const isLocked = ["0", "1"].includes(status);
            if (!isLocked) return;
            const row = el.closest('tr');
        
            fetch(`ajax-last-tasks/${objectId}/`)
                .then(response => response.json())
                .then(data => {
                    // 1. Update the HTML of the dropdown container
                    el.innerHTML = data.html;
                    const status = el.getAttribute('data-status');
                    // 3. Toggle row inputs based on new status
                    updateRowState(row, status);
                });
        });
    };

document.addEventListener('DOMContentLoaded', function() {

    // Run enforcement immediately on load
    document.querySelectorAll('.inline-block[id^="task-"]').forEach(el => {
        updateRowState(el.closest('tr'), el.getAttribute('data-status'));
    });

    // Start Polling every 5 seconds
    setInterval(pollStatus, 5000);
});


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
                     // Set to "completed"
                    input.style.backgroundColor = '#d4edda';
                    setTimeout(() => input.style.backgroundColor = '', 500);
                }
            });
        }
    }
});
