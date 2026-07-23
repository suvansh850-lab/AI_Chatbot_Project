// Morepen AI Chatbot Workspace - Frontend JavaScript
document.addEventListener('DOMContentLoaded', () => {
  // --- UI Elements ---
  const elLoginContainer = document.getElementById('login-container');
  const elLoginForm = document.getElementById('login-form');
  const elLoginError = document.getElementById('login-error');
  const elUsernameInput = document.getElementById('username');
  const elPasswordInput = document.getElementById('password');
  
  const elDashboardContainer = document.getElementById('dashboard-container');
  const elSidebar = document.getElementById('sidebar');
  const elToggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
  const elCloseSidebarBtn = document.getElementById('close-sidebar-btn');
  const elConversationsList = document.getElementById('conversations-list');
  const elNewChatBtn = document.getElementById('new-chat-btn');
  const elUserDisplayName = document.getElementById('user-display-name');
  const elLogoutBtn = document.getElementById('logout-btn');
  
  const elActiveChatTitle = document.getElementById('active-chat-title');
  const elDbStatusDot = document.getElementById('db-status-dot');
  const elDbStatusText = document.getElementById('db-status-text');
  
  const elProviderSelect = document.getElementById('provider-select');
  const elModelSelect = document.getElementById('model-select');
  const elClearChatBtn = document.getElementById('clear-chat-btn');
  
  const elChatHistory = document.getElementById('chat-history');
  const elWelcomeScreen = document.getElementById('welcome-screen');
  const elChatMessages = document.getElementById('chat-messages');
  
  const elAttachmentPreviewBar = document.getElementById('attachment-preview-bar');
  const elPreviewFilename = document.getElementById('preview-filename');
  const elPreviewIcon = document.getElementById('preview-icon');
  const elRemoveAttachmentBtn = document.getElementById('remove-attachment-btn');
  
  const elWebSearchToggle = document.getElementById('web-search-toggle');
  const elAttachDocBtn = document.getElementById('attach-doc-btn');
  const elAttachImgBtn = document.getElementById('attach-img-btn');
  const elDocFileInput = document.getElementById('doc-file-input');
  const elImgFileInput = document.getElementById('img-file-input');
  
  const elChatInput = document.getElementById('chat-input');
  const elVoiceBtn = document.getElementById('voice-btn');
  const elSendBtn = document.getElementById('send-btn');
  
  // --- Global State ---
  let state = {
    user: null,
    conversations: [],
    activeConversationId: null,
    models: {
      Gemini: null,
      Groq: null
    },
    selectedProvider: 'Gemini',
    selectedModel: '',
    attachedDoc: null, // { name, text }
    attachedImg: null, // { name, base64, mime }
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    audioContext: null
  };

  // Configure Marked Options
  if (window.marked) {
    marked.setOptions({
      breaks: true,
      gfm: true,
      headerIds: false,
      mangle: false
    });
  }

  // --- Initialization ---
  function init() {
    checkBackendHealth();
    
    // Check local storage for session
    const savedUser = localStorage.getItem('chat_user');
    if (savedUser) {
      try {
        state.user = JSON.parse(savedUser);
        showDashboard();
      } catch (e) {
        localStorage.removeItem('chat_user');
        showLogin();
      }
    } else {
      showLogin();
    }

    // Load available models for default provider
    fetchModels('Gemini');
    fetchModels('Groq');

    setupEventListeners();
  }

  // --- Health Checks ---
  async function checkBackendHealth() {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = await res.json();
        if (data.database && data.database.ok) {
          setDbStatus(true, 'Connected');
        } else {
          setDbStatus(false, 'DB Error: ' + (data.database.error || 'Check server configuration'));
        }
      } else {
        setDbStatus(false, 'API Server Error');
      }
    } catch (e) {
      setDbStatus(false, 'Cannot reach backend service');
    }
  }

  function setDbStatus(ok, message) {
    if (ok) {
      elDbStatusDot.className = 'status-dot green animated';
      elDbStatusText.textContent = 'Backend ' + message;
    } else {
      elDbStatusDot.className = 'status-dot red';
      elDbStatusText.textContent = message;
    }
  }

  // --- Views Switching ---
  function showLogin() {
    elLoginContainer.classList.remove('hidden');
    elDashboardContainer.classList.add('hidden');
    elUsernameInput.focus();
  }

  function showDashboard() {
    elLoginContainer.classList.add('hidden');
    elDashboardContainer.classList.remove('hidden');
    elUserDisplayName.textContent = state.user.username;
    
    // Fetch user's conversation threads
    loadConversations();
    
    // Reset inputs
    resetAttachment();
    elChatInput.value = '';
    adjustTextareaHeight();
  }

  // --- Event Listeners ---
  function setupEventListeners() {
    // Login Submission
    elLoginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = elUsernameInput.value.trim();
      const password = elPasswordInput.value.trim();
      
      elLoginError.classList.add('hidden');
      
      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        
        if (res.ok) {
          const data = await res.json();
          state.user = { id: data.user_id, username: data.username };
          localStorage.setItem('chat_user', JSON.stringify(state.user));
          showDashboard();
        } else {
          const err = await res.json();
          elLoginError.textContent = err.detail || 'Incorrect credentials';
          elLoginError.classList.remove('hidden');
        }
      } catch (err) {
        elLoginError.textContent = 'Connection failed';
        elLoginError.classList.remove('hidden');
      }
    });

    // Logout Button
    elLogoutBtn.addEventListener('click', () => {
      localStorage.removeItem('chat_user');
      state.user = null;
      state.conversations = [];
      state.activeConversationId = null;
      showLogin();
    });

    // Sidebar Toggles
    elToggleSidebarBtn.addEventListener('click', () => {
      elSidebar.classList.add('open');
    });
    elCloseSidebarBtn.addEventListener('click', () => {
      elSidebar.classList.remove('open');
    });

    // Suggestion Cards Clicking
    document.querySelectorAll('.suggestion-card').forEach(card => {
      card.addEventListener('click', () => {
        const prompt = card.getAttribute('data-prompt');
        elChatInput.value = prompt;
        adjustTextareaHeight();
        elChatInput.focus();
      });
    });

    // Provider Selector Changed
    elProviderSelect.addEventListener('change', (e) => {
      state.selectedProvider = e.target.value;
      updateModelDropdown();
    });

    // Model Selector Changed
    elModelSelect.addEventListener('change', (e) => {
      state.selectedModel = e.target.value;
    });

    // New Chat Button
    elNewChatBtn.addEventListener('click', () => {
      startNewChat();
    });

    // Clear Chat Messages Button
    elClearChatBtn.addEventListener('click', async () => {
      if (!state.activeConversationId) return;
      if (confirm('Clear all messages in this conversation thread?')) {
        try {
          const res = await fetch(`/api/conversations/${state.activeConversationId}/clear`, {
            method: 'DELETE'
          });
          if (res.ok) {
            renderMessages([]);
          }
        } catch (e) {
          alert('Error clearing messages');
        }
      }
    });

    // Document attachment trigger
    elAttachDocBtn.addEventListener('click', () => elDocFileInput.click());
    elDocFileInput.addEventListener('change', handleDocUpload);

    // Image attachment trigger
    elAttachImgBtn.addEventListener('click', () => elImgFileInput.click());
    elImgFileInput.addEventListener('change', handleImgUpload);

    // Remove attachment preview
    elRemoveAttachmentBtn.addEventListener('click', resetAttachment);

    // Dynamic Textarea Auto-expand
    elChatInput.addEventListener('input', adjustTextareaHeight);

    // Keyboard Shortcuts (Enter key sends, Shift+Enter inputs newline)
    elChatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Send Button Click
    elSendBtn.addEventListener('click', sendMessage);

    // Voice record button click
    elVoiceBtn.addEventListener('click', toggleVoiceRecording);
  }

  // --- Conversations Management ---
  async function loadConversations() {
    if (!state.user) return;
    try {
      const res = await fetch(`/api/conversations?user_id=${state.user.id}`);
      if (res.ok) {
        const data = await res.json();
        state.conversations = data.conversations || [];
        renderConversationsList();
        
        // Auto-select latest conversation or prompt a clean screen
        if (state.conversations.length > 0 && !state.activeConversationId) {
          selectConversation(state.conversations[0].id);
        } else if (state.conversations.length === 0) {
          startNewChat();
        }
      }
    } catch (e) {
      console.error('Error listing conversations', e);
    }
  }

  function renderConversationsList() {
    elConversationsList.innerHTML = '';
    state.conversations.forEach(conv => {
      const el = document.createElement('div');
      el.className = `conv-item ${state.activeConversationId === conv.id ? 'active' : ''}`;
      el.dataset.id = conv.id;
      
      const title = conv.title || 'New Chat';
      el.innerHTML = `
        <div class="conv-left">
          <i class="fa-solid fa-message conv-icon"></i>
          <span class="conv-title">${escapeHTML(title)}</span>
        </div>
        <button class="conv-delete-btn" title="Delete thread">
          <i class="fa-solid fa-trash"></i>
        </button>
      `;
      
      // Click selection handler
      el.querySelector('.conv-left').addEventListener('click', () => {
        selectConversation(conv.id);
        elSidebar.classList.remove('open'); // close sidebar on mobile
      });
      
      // Delete handler
      el.querySelector('.conv-delete-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteConversationThread(conv.id);
      });
      
      elConversationsList.appendChild(el);
    });
  }

  async function selectConversation(id) {
    state.activeConversationId = id;
    const active = state.conversations.find(c => c.id === id);
    
    // Set Header titles
    elActiveChatTitle.textContent = active ? (active.title || 'Chat Session') : 'New Chat';
    
    // Update active highlight
    document.querySelectorAll('.conv-item').forEach(el => {
      if (parseInt(el.dataset.id) === id) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });

    // Select correct provider if recorded in conversation meta
    if (active) {
      if (active.provider && (active.provider === 'Gemini' || active.provider === 'Groq')) {
        elProviderSelect.value = active.provider;
        state.selectedProvider = active.provider;
        updateModelDropdown();
        
        if (active.model_name) {
          elModelSelect.value = active.model_name;
          state.selectedModel = active.model_name;
        }
      }
    }

    // Load messages
    try {
      const res = await fetch(`/api/conversations/${id}/messages`);
      if (res.ok) {
        const data = await res.json();
        renderMessages(data.messages || []);
      }
    } catch (e) {
      console.error('Error fetching conversation messages', e);
    }
  }

  async function deleteConversationThread(id) {
    if (confirm('Delete this conversation thread permanently?')) {
      try {
        const res = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
        if (res.ok) {
          // If we deleted the active thread, reset to a clean state
          if (state.activeConversationId === id) {
            state.activeConversationId = null;
          }
          loadConversations();
        }
      } catch (e) {
        console.error('Error deleting conversation', e);
      }
    }
  }

  function startNewChat() {
    state.activeConversationId = null;
    elActiveChatTitle.textContent = 'New Chat';
    document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
    renderMessages([]);
  }

  // --- Model Retrieval ---
  async function fetchModels(provider) {
    try {
      const res = await fetch(`/models/${provider}`);
      if (res.ok) {
        const data = await res.json();
        state.models[provider] = data;
        if (provider === state.selectedProvider) {
          updateModelDropdown();
        }
      }
    } catch (e) {
      console.error(`Error loading models for ${provider}`, e);
    }
  }

  function updateModelDropdown() {
    const data = state.models[state.selectedProvider];
    elModelSelect.innerHTML = '';
    
    if (data && data.available_models) {
      data.available_models.forEach(model => {
        const opt = document.createElement('option');
        opt.value = model;
        opt.textContent = model;
        if (model === data.active_model) {
          opt.selected = true;
          state.selectedModel = model;
        }
        elModelSelect.appendChild(opt);
      });
    } else {
      const opt = document.createElement('option');
      opt.textContent = 'Default Model';
      opt.value = '';
      elModelSelect.appendChild(opt);
      state.selectedModel = '';
    }
  }

  // --- Attachment Handlers ---
  function handleDocUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    // Reset image if attached
    state.attachedImg = null;
    
    const reader = new FileReader();
    reader.onload = function(evt) {
      state.attachedDoc = {
        name: file.name,
        text: evt.target.result
      };
      showAttachmentPreview('doc', file.name);
    };
    reader.readAsText(file);
  }

  function handleImgUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    // Reset document if attached
    state.attachedDoc = null;
    
    const reader = new FileReader();
    reader.onload = function(evt) {
      const base64Data = evt.target.result.split(',')[1];
      state.attachedImg = {
        name: file.name,
        base64: base64Data,
        mime: file.type
      };
      showAttachmentPreview('img', file.name);
    };
    reader.readAsDataURL(file);
  }

  function showAttachmentPreview(type, filename) {
    elPreviewFilename.textContent = filename;
    if (type === 'img') {
      elPreviewIcon.innerHTML = '<i class="fa-solid fa-image"></i>';
    } else {
      elPreviewIcon.innerHTML = '<i class="fa-solid fa-file-lines"></i>';
    }
    elAttachmentPreviewBar.classList.remove('hidden');
    adjustTextareaHeight();
  }

  function resetAttachment() {
    state.attachedDoc = null;
    state.attachedImg = null;
    elDocFileInput.value = '';
    elImgFileInput.value = '';
    elAttachmentPreviewBar.classList.add('hidden');
    adjustTextareaHeight();
  }

  // --- Voice Transcription (Speech-To-Text) ---
  async function toggleVoiceRecording() {
    if (state.isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  }

  async function startVoiceRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.audioChunks = [];
      state.mediaRecorder = new MediaRecorder(stream);
      
      state.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          state.audioChunks.push(e.data);
        }
      };

      state.mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(state.audioChunks, { type: 'audio/wav' });
        stream.getTracks().forEach(track => track.stop());
        
        // Transcribe WAV audio
        transcribeAudioBlob(audioBlob);
      };

      state.mediaRecorder.start();
      state.isRecording = true;
      elVoiceBtn.className = 'btn-circle btn-voice recording';
      elVoiceBtn.title = 'Stop Recording';
    } catch (e) {
      alert('Unable to access microphone. Check permissions.');
      console.error(e);
    }
  }

  function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecording) {
      state.mediaRecorder.stop();
      state.isRecording = false;
      elVoiceBtn.className = 'btn-circle btn-voice';
      elVoiceBtn.title = 'Speak to Transcribe';
    }
  }

  async function transcribeAudioBlob(blob) {
    // Show spinner in input
    elChatInput.placeholder = 'Transcribing voice input...';
    elChatInput.disabled = true;
    
    try {
      const base64Data = await convertBlobToBase64(blob);
      const res = await fetch('/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_base64: base64Data,
          mime_type: 'audio/wav',
          provider: 'Gemini'
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        if (data.text) {
          elChatInput.value = data.text;
          adjustTextareaHeight();
        }
      } else {
        const err = await res.json();
        console.error('Transcription failed', err);
      }
    } catch (e) {
      console.error('Error transcribing audio', e);
    } finally {
      elChatInput.placeholder = 'Type a message or press the microphone to speak...';
      elChatInput.disabled = false;
      elChatInput.focus();
    }
  }

  function convertBlobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result.split(',')[1];
        resolve(base64String);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  // --- Rendering UI Messages ---
  function renderMessages(messages) {
    if (messages.length === 0) {
      elWelcomeScreen.classList.remove('hidden');
      elChatMessages.classList.add('hidden');
      elChatMessages.innerHTML = '';
      return;
    }

    elWelcomeScreen.classList.add('hidden');
    elChatMessages.classList.remove('hidden');
    elChatMessages.innerHTML = '';

    messages.forEach(msg => {
      appendMessageBubble(msg.role, msg.content, false);
    });

    scrollToBottom();
  }

  function appendMessageBubble(role, content, animate = true) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${role} ${animate ? 'animate-fade-in' : ''}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.innerHTML = role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';
    
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    
    // Parse Markdown content
    let htmlContent = content;
    if (window.marked) {
      htmlContent = marked.parse(content);
    }
    
    bubble.innerHTML = htmlContent;
    
    // Code blocks post-processing: add copies & labels
    enhanceCodeBlocks(bubble);

    // Render report download buttons if download link is detected
    const reportRegex = /\/reports\/report_[a-f0-9]{8}\.(pdf|xlsx|pptx)/g;
    const matches = content.match(reportRegex);
    if (matches) {
      matches.forEach(url => {
        const fileExt = url.split('.').pop().toUpperCase();
        const filename = `Document_Export_${url.split('_').pop()}`;
        const card = createReportDownloadCard(filename, url);
        bubble.appendChild(card);
      });
    }

    // Add Speech (TTS) utilities on assistant bubbles
    if (role === 'assistant') {
      const controls = document.createElement('div');
      controls.className = 'bubble-controls';
      controls.innerHTML = `
        <button class="bubble-btn tts-btn" title="Synthesize text to speech">
          <i class="fa-solid fa-volume-high"></i> Speak
        </button>
        <button class="bubble-btn copy-txt-btn" title="Copy text to clipboard">
          <i class="fa-solid fa-copy"></i> Copy
        </button>
      `;
      
      // Hook controls
      controls.querySelector('.tts-btn').addEventListener('click', () => speakMessageText(content, controls.querySelector('.tts-btn')));
      controls.querySelector('.copy-txt-btn').addEventListener('click', () => copyToClipboard(content, controls.querySelector('.copy-txt-btn')));
      
      bubble.appendChild(controls);
    }

    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    elChatMessages.appendChild(wrapper);
  }

  function createReportDownloadCard(filename, downloadUrl) {
    const card = document.createElement('div');
    card.className = 'doc-info-tag report-download-card';
    card.style.marginTop = '10px';
    card.style.display = 'flex';
    card.style.alignItems = 'center';
    card.style.gap = '10px';
    card.style.background = 'rgba(255, 255, 255, 0.05)';
    card.style.border = '1px solid var(--border)';
    card.style.borderRadius = '8px';
    card.style.padding = '8px 12px';
    
    card.innerHTML = `
      <i class="fa-solid fa-file-arrow-down" style="font-size: 1.3rem; color: var(--primary);"></i>
      <div style="flex: 1; text-align: left;">
        <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-main);">${escapeHTML(filename)}</div>
        <div style="font-size: 0.7rem; color: var(--text-secondary);">Click button to download</div>
      </div>
      <a href="${downloadUrl}" download style="
        background: var(--primary);
        color: #fff;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.75rem;
        text-decoration: none;
        font-weight: 500;
        transition: var(--transition-fast);
      " onmouseover="this.style.background='var(--primary-hover)'" onmouseout="this.style.background='var(--primary)'">
        Download
      </a>
    `;
    return card;
  }

  function enhanceCodeBlocks(container) {
    const codeBlocks = container.querySelectorAll('pre');
    codeBlocks.forEach(pre => {
      const code = pre.querySelector('code');
      if (!code) return;
      
      // Determine language
      const classes = code.className || '';
      const match = classes.match(/language-(\w+)/);
      const lang = match ? match[1] : 'code';

      // Create header
      const header = document.createElement('div');
      header.className = 'code-block-header';
      header.innerHTML = `
        <span>${lang.toUpperCase()}</span>
        <button class="code-copy-btn">
          <i class="fa-solid fa-copy"></i> Copy
        </button>
      `;

      // Copy click handler
      header.querySelector('.code-copy-btn').addEventListener('click', () => {
        navigator.clipboard.writeText(code.textContent).then(() => {
          const btn = header.querySelector('.code-copy-btn');
          btn.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
          setTimeout(() => {
            btn.innerHTML = '<i class="fa-solid fa-copy"></i> Copy';
          }, 2000);
        });
      });

      pre.parentNode.insertBefore(header, pre);
    });
  }

  // --- Text-To-Speech Playback ---
  async function speakMessageText(text, btnElement) {
    // Strip markdown formatting simple regex
    const cleanText = text.replace(/[*#`_\-]/g, '').trim();
    if (!cleanText) return;

    btnElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading...';
    btnElement.disabled = true;

    try {
      const res = await fetch('/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: cleanText,
          voice: 'Alice',
          provider: 'Edge-TTS'
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        const audioSrc = `data:audio/mp3;base64,${data.audio_base64}`;
        const audio = new Audio(audioSrc);
        
        btnElement.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speaking...';
        
        audio.onended = () => {
          btnElement.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
          btnElement.disabled = false;
        };
        
        audio.play();
      } else {
        btnElement.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Error';
        setTimeout(() => {
          btnElement.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
          btnElement.disabled = false;
        }, 2000);
      }
    } catch (e) {
      console.error('TTS error', e);
      btnElement.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
      btnElement.disabled = false;
    }
  }

  function copyToClipboard(text, btnElement) {
    navigator.clipboard.writeText(text).then(() => {
      btnElement.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
      setTimeout(() => {
        btnElement.innerHTML = '<i class="fa-solid fa-copy"></i> Copy';
      }, 2000);
    });
  }

  // --- Send Message logic ---
  async function sendMessage() {
    const textPrompt = elChatInput.value.trim();
    if (!textPrompt && !state.attachedImg && !state.attachedDoc) return;
    
    // Check and create conversation if not exists
    if (!state.activeConversationId) {
      const convTitle = textPrompt ? (textPrompt.substring(0, 24) + '...') : 'Attachment chat';
      try {
        const res = await fetch('/api/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: state.user.id,
            title: convTitle,
            provider: state.selectedProvider,
            model_name: state.selectedModel
          })
        });
        
        if (res.ok) {
          const data = await res.json();
          state.activeConversationId = data.conversation_id;
          
          // Refresh list silently
          await loadConversations();
          
          // Force highlight selecting this newly created conversation
          state.activeConversationId = data.conversation_id;
          elActiveChatTitle.textContent = convTitle;
        } else {
          alert('Could not start a conversation thread.');
          return;
        }
      } catch (e) {
        console.error('Error starting conversation', e);
        return;
      }
    }

    // Capture prompt elements & attach state
    const provider = state.selectedProvider;
    const model = state.selectedModel;
    const conversationId = state.activeConversationId;
    const isWebSearch = elWebSearchToggle.checked;
    
    let docText = "";
    if (state.attachedDoc) {
      docText = `[File attached: ${state.attachedDoc.name}]\n\n${state.attachedDoc.text}`;
    }
    
    let base64Img = null;
    let mimeImg = null;
    if (state.attachedImg) {
      base64Img = state.attachedImg.base64;
      mimeImg = state.attachedImg.mime;
    }

    // Immediately display user message in chat
    let displayPrompt = textPrompt;
    if (state.attachedDoc) {
      displayPrompt = `<div class="doc-info-tag"><i class="fa-solid fa-file-lines"></i> ${escapeHTML(state.attachedDoc.name)}</div> ${escapeHTML(textPrompt)}`;
    } else if (state.attachedImg) {
      displayPrompt = `<img src="data:${state.attachedImg.mime};base64,${state.attachedImg.base64}" class="bubble-img"><br>${escapeHTML(textPrompt)}`;
    }
    
    elWelcomeScreen.classList.add('hidden');
    elChatMessages.classList.remove('hidden');
    
    appendMessageBubble('user', displayPrompt, true);
    scrollToBottom();
    
    // Clear inputs immediately
    elChatInput.value = '';
    resetAttachment();
    adjustTextareaHeight();
    
    // Display assistant typing skeleton bubble
    const typingWrapper = document.createElement('div');
    typingWrapper.className = 'message-wrapper assistant animate-fade-in';
    typingWrapper.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="msg-bubble">
        <div style="display: flex; gap: 6px; padding: 4px 0;">
          <span style="animation: pulse-green 1.2s infinite; width: 8px; height: 8px; border-radius: 50%; background: var(--primary);"></span>
          <span style="animation: pulse-green 1.2s infinite; animation-delay: 0.2s; width: 8px; height: 8px; border-radius: 50%; background: var(--primary);"></span>
          <span style="animation: pulse-green 1.2s infinite; animation-delay: 0.4s; width: 8px; height: 8px; border-radius: 50%; background: var(--primary);"></span>
        </div>
      </div>
    `;
    elChatMessages.appendChild(typingWrapper);
    scrollToBottom();

    // Call /chat endpoint
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: textPrompt,
          provider: provider,
          conversation_id: conversationId,
          messages: [], // server handles database context loading itself
          document_text: docText,
          data_context: "",
          image_base64: base64Img,
          image_mime: mimeImg,
          web_search: isWebSearch
        })
      });

      // Remove typing bubble
      typingWrapper.remove();

      if (res.ok) {
        const data = await res.json();
        appendMessageBubble('assistant', data.answer, true);
        scrollToBottom();
      } else {
        const err = await res.json();
        appendMessageBubble('assistant', `⚠️ **Error generating response**: ${err.detail || 'Server encountered an issue'}`, true);
        scrollToBottom();
      }
    } catch (e) {
      typingWrapper.remove();
      appendMessageBubble('assistant', `⚠️ **Network Error**: Unable to establish connection to the AI gateway.`, true);
      scrollToBottom();
    }
  }

  // --- Helpers ---
  function adjustTextareaHeight() {
    elChatInput.style.height = 'auto';
    elChatInput.style.height = (elChatInput.scrollHeight) + 'px';
  }

  function scrollToBottom() {
    elChatHistory.scrollTop = elChatHistory.scrollHeight;
  }

  function escapeHTML(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Run initial setup
  init();
});
