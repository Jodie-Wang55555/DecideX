// 决策助手页面逻辑

const state = {
    messages: [],
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    apiBaseUrl: 'http://localhost:8123',
    conversationId: null
};

const elements = {
    messagesContainer: document.getElementById('messages-container'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    voiceBtn: document.getElementById('voice-btn'),
    voiceModal: document.getElementById('voice-modal'),
    stopVoiceBtn: document.getElementById('stop-voice-btn'),
    charCount: document.getElementById('char-count'),
    typingIndicator: document.getElementById('typing-indicator'),
    costStatus: document.getElementById('cost-status'),
    riskStatus: document.getElementById('risk-status'),
    valueStatus: document.getElementById('value-status')
};

// 初始化
function init() {
    setupEventListeners();
    loadMessages();
    autoResizeTextarea();
    updateAnalysisStatus('waiting');
}

function setupEventListeners() {
    // 发送消息
    elements.sendBtn.addEventListener('click', sendMessage);
    elements.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // 字符计数
    elements.messageInput.addEventListener('input', () => {
        const count = elements.messageInput.value.length;
        elements.charCount.textContent = count;
        elements.sendBtn.disabled = count === 0;
    });

    // 语音输入
    elements.voiceBtn.addEventListener('click', toggleVoiceRecording);
    elements.stopVoiceBtn.addEventListener('click', stopVoiceRecording);

    // 示例问题
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.dataset.question;
            elements.messageInput.value = question;
            elements.charCount.textContent = question.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        });
    });
}

function autoResizeTextarea() {
    elements.messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message) return;

    // 添加用户消息
    addMessage('user', message);
    
    // 清空输入框
    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
    elements.charCount.textContent = '0';
    elements.sendBtn.disabled = true;
    
    // 更新分析状态
    updateAnalysisStatus('analyzing');
    
    // 显示加载状态
    showTypingIndicator();
    
    // 保存消息
    saveMessages();
    
    try {
        const response = await fetch(`${state.apiBaseUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                agent: 'decision',
                message: message,
                conversation_id: state.conversationId || getConversationId()
            })
        });

        if (!response.ok) {
            throw new Error('网络请求失败');
        }

        const data = await response.json();
        
        // 隐藏加载状态
        hideTypingIndicator();
        
        // 更新分析状态
        updateAnalysisStatus('completed');
        
        // 添加助手回复
        addMessage('assistant', data.response || data.message || '抱歉，我无法处理您的请求。');
        
        // 保存会话ID
        if (data.conversation_id) {
            state.conversationId = data.conversation_id;
        }
        
    } catch (error) {
        console.error('发送消息失败:', error);
        hideTypingIndicator();
        updateAnalysisStatus('error');
        addMessage('assistant', '抱歉，发生了错误。请检查网络连接或确保后端服务正在运行。');
    }
    
    saveMessages();
}

function addMessage(role, content) {
    // 移除欢迎消息
    const welcomeMsg = elements.messagesContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    // 处理换行
    const lines = content.split('\n');
    lines.forEach((line, index) => {
        if (line.trim()) {
            const p = document.createElement('p');
            p.textContent = line;
            p.style.marginBottom = index < lines.length - 1 ? '0.5rem' : '0';
            messageContent.appendChild(p);
        } else if (index < lines.length - 1) {
            messageContent.appendChild(document.createElement('br'));
        }
    });
    
    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = new Date().toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(messageContent);
    messageContent.appendChild(messageTime);
    
    elements.messagesContainer.appendChild(messageDiv);
    
    // 滚动到底部
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
    
    // 保存到状态
    state.messages.push({ role, content, timestamp: Date.now() });
}

function showTypingIndicator() {
    elements.typingIndicator.classList.add('active');
}

function hideTypingIndicator() {
    elements.typingIndicator.classList.remove('active');
}

function updateAnalysisStatus(status) {
    const statusText = {
        'waiting': '等待中',
        'analyzing': '分析中...',
        'completed': '已完成',
        'error': '错误'
    };
    
    const statusClass = {
        'waiting': '',
        'analyzing': 'active',
        'completed': 'active',
        'error': ''
    };
    
    [elements.costStatus, elements.riskStatus, elements.valueStatus].forEach(el => {
        el.textContent = statusText[status] || '等待中';
        el.className = 'analysis-status ' + (statusClass[status] || '');
    });
}

function toggleVoiceRecording() {
    if (state.isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

async function startVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.mediaRecorder = new MediaRecorder(stream);
        state.audioChunks = [];
        
        state.mediaRecorder.ondataavailable = (event) => {
            state.audioChunks.push(event.data);
        };
        
        state.mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(state.audioChunks, { type: 'audio/wav' });
            await processAudioInput(audioBlob);
            stream.getTracks().forEach(track => track.stop());
        };
        
        state.mediaRecorder.start();
        state.isRecording = true;
        
        elements.voiceBtn.classList.add('recording');
        elements.voiceModal.classList.add('active');
        
    } catch (error) {
        console.error('无法访问麦克风:', error);
        alert('无法访问麦克风。请检查浏览器权限设置。');
    }
}

function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;
        
        elements.voiceBtn.classList.remove('recording');
        elements.voiceModal.classList.remove('active');
    }
}

async function processAudioInput(audioBlob) {
    showTypingIndicator();
    
    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');
        formData.append('agent', 'decision');
        
        const response = await fetch(`${state.apiBaseUrl}/transcribe`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('语音识别失败');
        }
        
        const data = await response.json();
        const transcribedText = data.text || data.transcription;
        
        if (transcribedText) {
            elements.messageInput.value = transcribedText;
            elements.charCount.textContent = transcribedText.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        } else {
            hideTypingIndicator();
            addMessage('assistant', '抱歉，无法识别您的语音。请重试。');
        }
        
    } catch (error) {
        console.error('处理音频失败:', error);
        hideTypingIndicator();
        tryBrowserSpeechRecognition();
    }
}

function tryBrowserSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        
        recognition.lang = 'zh-CN';
        recognition.continuous = false;
        recognition.interimResults = false;
        
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            elements.messageInput.value = transcript;
            elements.charCount.textContent = transcript.length;
            elements.sendBtn.disabled = false;
            sendMessage();
        };
        
        recognition.onerror = (event) => {
            console.error('语音识别错误:', event.error);
            hideTypingIndicator();
            addMessage('assistant', '语音识别失败，请重试或直接输入文字。');
        };
        
        recognition.start();
    } else {
        hideTypingIndicator();
        addMessage('assistant', '您的浏览器不支持语音识别功能。');
    }
}

function getConversationId() {
    if (!state.conversationId) {
        state.conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('conversationId', state.conversationId);
    }
    return state.conversationId;
}

function saveMessages() {
    localStorage.setItem('decision_messages', JSON.stringify(state.messages));
}

function loadMessages() {
    const savedMessages = localStorage.getItem('decision_messages');
    if (savedMessages) {
        try {
            state.messages = JSON.parse(savedMessages);
            state.messages.forEach(msg => {
                addMessage(msg.role, msg.content);
            });
        } catch (error) {
            console.error('加载消息失败:', error);
        }
    }
    
    const savedConvId = localStorage.getItem('conversationId');
    if (savedConvId) {
        state.conversationId = savedConvId;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 处理页面可见性变化
document.addEventListener('visibilitychange', () => {
    if (document.hidden && state.isRecording) {
        stopVoiceRecording();
    }
});
