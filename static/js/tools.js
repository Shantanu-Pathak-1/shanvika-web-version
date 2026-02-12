function openToolsModal() {
    const modal = document.getElementById('tools-modal');
    if(modal) modal.style.display = 'flex';
}

function selectTool(toolName) {
    if (typeof setMode === 'function') currentMode = toolName;
    else window.currentMode = toolName;

    const input = document.getElementById('user-input');
    const uploadBtn = document.getElementById('file-upload');
    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));

    switch(toolName) {
        case 'resume_analyzer':
            input.placeholder = "📄 Upload PDF Resume & press send...";
            if(uploadBtn) uploadBtn.click();
            Swal.fire({toast:true, position:'top-end', icon:'info', title:'Upload Resume (PDF)', showConfirmButton:false, timer:3000});
            break;
        case 'youtube_summarizer': input.placeholder = "📺 Paste YouTube Link..."; input.focus(); break;
        case 'mock_interviewer': input.placeholder = "🎓 Enter Role (e.g. Java Dev) to START..."; input.focus(); break;
        case 'interview_questions': input.placeholder = "📋 Enter Role for Questions..."; input.focus(); break;
        case 'github_review': input.placeholder = "🐙 Paste GitHub Link..."; input.focus(); break;
        case 'currency_converter': input.placeholder = "💱 E.g. 100 USD to INR..."; input.focus(); break;
        case 'password_generator': input.placeholder = "🔐 Press send for password..."; input.focus(); break;
        case 'grammar_fixer': input.placeholder = "📝 Paste text to fix..."; input.focus(); break;
        case 'qr_generator': input.placeholder = "🔗 Enter text/link..."; input.focus(); break;
        case 'prompt_writer': input.placeholder = "✨ Describe idea..."; input.focus(); break;
        default: input.placeholder = `Using ${toolName}...`;
    }
    closeModal('tools-modal');
    Swal.fire({toast:true, position:'top-end', icon:'success', title:`Switched to ${toolName.replace('_',' ')}`, showConfirmButton:false, timer:1500});
}