document.addEventListener('DOMContentLoaded', function() {
    const handleUpdate = async (input) => {
        const wrapper = input.closest('.ajax-section-wrapper');
        const indicator = wrapper.querySelector('.ajax-status-indicator');
        
        const data = new URLSearchParams();
        data.append('_id', input.dataset.id);
        data.append('_model_label', input.dataset.model);
        data.append('_field', input.dataset.field);
        data.append('_value', input.value);

        // Visual feedback: Start
        input.classList.add('opacity-50');
        indicator.textContent = 'Saving...';
        indicator.classList.remove('hidden', 'text-red-500');
        indicator.classList.add('text-gray-400');

        try {
            const response = await fetch('ajax-section-update/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: data
            });

            const result = await response.json();

            if (response.ok) {
                // Success feedback
                input.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
                indicator.textContent = 'Saved';
                indicator.classList.replace('text-gray-400', 'text-green-500');
                setTimeout(() => {
                    input.style.backgroundColor = '';
                    indicator.classList.add('hidden');
                }, 2000);
            } else {
                throw new Error(result.error || 'Update failed');
            }
        } catch (error) {
            console.error('Section AJAX Error:', error);
            indicator.textContent = 'Error';
            indicator.classList.replace('text-gray-400', 'text-red-500');
            input.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
        } finally {
            input.classList.remove('opacity-50');
        }
    };

    document.addEventListener('keydown', function(e) {
        if (e.target.classList.contains('section-ajax-input') && e.key === 'Enter') {
            e.preventDefault();
            handleUpdate(e.target);
            e.target.blur();
        }
    });

    document.addEventListener('focusout', function(e) {
        if (e.target.classList.contains('section-ajax-input')) {
            handleUpdate(e.target);
        }
    });
});