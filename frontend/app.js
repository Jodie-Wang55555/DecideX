// 应用状态
const state = {
    currentAgent: 'customer',
    messages: [],
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    apiBaseUrl: 'http://localhost:8123' // 后端代理服务地址（默认与 LangGraph Dev Studio 相同）
};

// 智能体配置
const agents = {
    customer: {
        name: '客户支持智能体',
        icon: '💬',
        description: '处理客户咨询和服务请求'
    },
    doctor: {
        name: '医生预约智能体',
        icon: '🏥',
        description: '帮助您预约和管理医生就诊'
    },
    booking: {
        name: '预订服务智能体',
        icon: '📅',
        description: '协助您进行各种预订服务'
    }
};

// DOM 元素
const elements = {
    agentButtons: document.querySelectorAll('.agent-btn'),
    currentAgentName: document.getElementById('current-agent-name'),
    messagesContainer: document.getElementById('messages-container'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    voiceBtn: document.getElementById('voice-btn'),
    clearChatBtn: document.getElementById('clear-chat'),
    voiceModal: document.getElementById('voice-modal'),
    stopVoiceBtn: document.getElementById('stop-voice-btn'),
    charCount: document.getElementById('char-count'),
    typingIndicator: document.getElementById('typing-indicator')
};

// 初始化
function init() {
    setupEventListeners();
    loadMessages();
    autoResizeTextarea();
}

// 设置事件监听器
function setupEventListeners() {
    // 智能体切换
    elements.agentButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const agent = btn.dataset.agent;
            switchAgent(agent);
        });
    });

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

    // 清空对话
    elements.clearChatBtn.addEventListener('click', clearChat);
}

// 自动调整文本区域高度
function autoResizeTextarea() {
    elements.messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
}

// 切换智能体
function switchAgent(agent) {
    state.currentAgent = agent;
    
    // 更新按钮状态
    elements.agentButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.agent === agent);
    });
    
    // 更新标题
    elements.currentAgentName.textContent = agents[agent].name;
    
    // 保存当前智能体
    localStorage.setItem('currentAgent', agent);
}

// 发送消息
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
    
    // 显示加载状态
    showTypingIndicator();
    
    // 保存消息
    saveMessages();
    
    try {
        // 调用后端API
        const response = await fetch(`${state.apiBaseUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                agent: state.currentAgent,
                message: message,
                conversation_id: getConversationId()
            })
        });

        if (!response.ok) {
            throw new Error('网络请求失败');
        }

        const data = await response.json();
        
        // 隐藏加载状态
        hideTypingIndicator();
        
        // 添加助手回复
        addMessage('assistant', data.response || data.message || '抱歉，我无法处理您的请求。');
        
    } catch (error) {
        console.error('发送消息失败:', error);
        hideTypingIndicator();
        addMessage('assistant', '抱歉，发生了错误。请检查网络连接或稍后重试。');
    }
    
    saveMessages();
}

// 添加消息到界面
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
    avatar.textContent = role === 'user' ? '👤' : agents[state.currentAgent].icon;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    messageContent.textContent = content;
    
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

// 显示输入指示器
function showTypingIndicator() {
    elements.typingIndicator.classList.add('active');
}

// 隐藏输入指示器
function hideTypingIndicator() {
    elements.typingIndicator.classList.remove('active');
}

// 切换语音录制
async function toggleVoiceRecording() {
    if (state.isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

// 开始语音录制
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
            
            // 停止所有音频轨道
            stream.getTracks().forEach(track => track.stop());
        };
        
        state.mediaRecorder.start();
        state.isRecording = true;
        
        // 更新UI
        elements.voiceBtn.classList.add('recording');
        elements.voiceModal.classList.add('active');
        
    } catch (error) {
        console.error('无法访问麦克风:', error);
        alert('无法访问麦克风。请检查浏览器权限设置。');
    }
}

// 停止语音录制
function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;
        
        // 更新UI
        elements.voiceBtn.classList.remove('recording');
        elements.voiceModal.classList.remove('active');
    }
}

// 处理音频输入
async function processAudioInput(audioBlob) {
    showTypingIndicator();
    
    try {
        // 将音频转换为文本（这里需要调用语音识别API）
        // 示例：使用Web Speech API（浏览器内置）
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');
        formData.append('agent', state.currentAgent);
        
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
            // 将转录的文本添加到输入框
            elements.messageInput.value = transcribedText;
            elements.charCount.textContent = transcribedText.length;
            elements.sendBtn.disabled = false;
            
            // 自动发送
            sendMessage();
        } else {
            hideTypingIndicator();
            addMessage('assistant', '抱歉，无法识别您的语音。请重试。');
        }
        
    } catch (error) {
        console.error('处理音频失败:', error);
        hideTypingIndicator();
        
        // 如果后端不支持，尝试使用浏览器内置的语音识别
        tryBrowserSpeechRecognition();
    }
}

// 使用浏览器内置语音识别（备用方案）
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

// 清空对话
function clearChat() {
    if (confirm('确定要清空所有对话记录吗？')) {
        state.messages = [];
        elements.messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">🤖</div>
                <h3>欢迎使用 DecideX</h3>
                <p>选择一个智能体开始对话，或直接输入您的问题</p>
            </div>
        `;
        localStorage.removeItem('messages');
        localStorage.removeItem('conversationId');
    }
}

// 保存消息
function saveMessages() {
    localStorage.setItem('messages', JSON.stringify(state.messages));
}

// 加载消息
function loadMessages() {
    const savedMessages = localStorage.getItem('messages');
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
    
    // 加载当前智能体
    const savedAgent = localStorage.getItem('currentAgent');
    if (savedAgent && agents[savedAgent]) {
        switchAgent(savedAgent);
    }
}

// 获取对话ID
function getConversationId() {
    let conversationId = localStorage.getItem('conversationId');
    if (!conversationId) {
        conversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('conversationId', conversationId);
    }
    return conversationId;
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 处理页面可见性变化（暂停/恢复录音）
document.addEventListener('visibilitychange', () => {
    if (document.hidden && state.isRecording) {
        stopVoiceRecording();
    }
});
