// static/js/tools.js

// Tools Modal Open Logic
function openToolsModal() {
    const modal = document.getElementById('tools-modal');
    if(modal) {
        modal.style.display = 'flex';
        // Optional: Add entrance animation logic here if needed
    }
}

// Main Tool Selection Logic
function selectTool(toolName) {
    // 1. Update Global Mode (Variable script.js mein hai)
    if (typeof setMode === 'function') {
        // Hum dummy button pass kar rahe hain null ki jagah taaki error na aaye
        // Lekin UI update hum manually karenge
        currentMode = toolName;
    }

    // 2. UI Updates
    const input = document.getElementById('user-input');
    const uploadBtn = document.getElementById('file-upload');
    
    // Reset Active States on Main Bar
    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));

    // Tool Specific UI Changes
    switch(toolName) {
        case 'qr_generator':
            input.placeholder = "🔗 Paste link or text to generate QR code...";
            input.focus();
            break;
        case 'prompt_writer':
            input.placeholder = "✨ Describe your idea roughly (e.g. 'cat in space')...";
            input.focus();
            break;
        case 'converter':
            input.placeholder = "📂 Upload a file to convert (PDF, DOCX, IMG)...";
            // Auto click upload for converter
            if(uploadBtn) uploadBtn.click();
            break;
        default:
            input.placeholder = `Using Tool: ${toolName}`;
    }

    // 3. Close Modal
    closeModal('tools-modal');

    // 4. Show Feedback Toast
    const toolTitle = toolName.replace('_', ' ').toUpperCase();
    const Toast = Swal.mixin({
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: 2000,
        timerProgressBar: true,
        didOpen: (toast) => {
            toast.addEventListener('mouseenter', Swal.stopTimer)
            toast.addEventListener('mouseleave', Swal.resumeTimer)
        }
    });

    Toast.fire({
        icon: 'success',
        title: `Activated: ${toolTitle}`
    });
}