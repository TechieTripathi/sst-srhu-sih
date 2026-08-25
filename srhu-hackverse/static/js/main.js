/**
 * TechForge 3.0 Main JavaScript
 * Global utilities and helpers
 */

// Mobile sidebar toggle
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Modal utilities
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Close modal on backdrop click
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-backdrop')) {
        e.target.style.display = 'none';
        document.body.style.overflow = '';
    }
});

// Confirmation dialog
function confirm_action(message) {
    return window.confirm(message);
}

// Format score for display
function formatScore(score, scale = 100) {
    return (parseFloat(score) || 0).toFixed(2);
}

// Calculate weighted score
function calculateWeightedScore(scores, criteria) {
    let weighted = 0;
    criteria.forEach(c => {
        const score = parseFloat(scores[c.id]) || 0;
        weighted += score * c.weight;
    });
    return weighted;
}

// Validate score range
function validateScore(score, min = 0, max = 10) {
    const num = parseFloat(score);
    return !isNaN(num) && num >= min && num <= max;
}

// Loading state helpers
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = '<div class="loading-spinner"></div>';
        element.style.position = 'relative';
        element.appendChild(overlay);
    }
}

function hideLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        const overlay = element.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

// Toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `flash-message flash-message-${type}`;
    toast.textContent = message;
    
    let container = document.querySelector('.flash-messages');
    if (!container) {
        container = document.createElement('div');
        container.className = 'flash-messages';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// API request helper
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Export utilities
window.TechForge = {
    toggleSidebar,
    openModal,
    closeModal,
    formatScore,
    calculateWeightedScore,
    validateScore,
    showLoading,
    hideLoading,
    showToast,
    apiRequest,
    confirm_action
};
