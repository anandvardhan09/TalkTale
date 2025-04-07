// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
  // DOM Elements
  const chatInput = document.getElementById('chat-input');
  const sendButton = document.getElementById('send-button');
  const messagesContainer = document.getElementById('messages');
  const welcomeMessage = document.getElementById('welcome-message');
  const micToggle = document.getElementById('checkbox');
  const newChatBtn = document.getElementById('new-chat-btn');
  const chatHistoryList = document.getElementById('chat-history');
  const toggleBtn = document.getElementById('toggle-btn');
  const sidebar = document.querySelector('.sidebar');
  const audioPlayer = document.getElementById('audio-player');
  const feedbackPanel = document.getElementById('feedback-panel');
  const closeFeedbackBtn = document.getElementById('close-feedback');
  
  // Feedback elements
  const improvementsContent = document.getElementById('improvements-content');
  const suggestionsContent = document.getElementById('suggestions-content');
  const speechRateEl = document.getElementById('speech-rate');
  const speakingTimeEl = document.getElementById('speaking-time');
  const pauseCountEl = document.getElementById('pause-count');
  const errorRateEl = document.getElementById('error-rate');
  
  // State variables
  let currentChatId = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  
  // Create a new chat on page load
  createNewChat('general topics');
  
  // Event Listeners
  toggleBtn.addEventListener('click', toggleSidebar);
  newChatBtn.addEventListener('click', () => {
      const topic = prompt('What topics are you interested in?', 'general topics');
      if (topic) {
          createNewChat(topic);
      }
  });
  
  sendButton.addEventListener('click', sendMessage);
  chatInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
      }
  });
  
  micToggle.addEventListener('change', toggleRecording);
  
  closeFeedbackBtn.addEventListener('click', () => {
      feedbackPanel.classList.add('hidden');
  });
  
  // Functions
  function toggleSidebar() {
      sidebar.classList.toggle('active');
  }
  
  function createNewChat(interests) {
      fetch('/api/new-chat', {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json'
          },
          body: JSON.stringify({ interests: interests })
      })
      .then(response => response.json())
      .then(data => {
          currentChatId = data.chatId;
          loadChat(data.chatId);
          updateChatList();
      })
      .catch(error => console.error('Error creating chat:', error));
  }
  
  function updateChatList() {
      fetch('/api/chats')
      .then(response => response.json())
      .then(chats => {
          chatHistoryList.innerHTML = '';
          chats.forEach(chat => {
              const li = document.createElement('li');
              li.textContent = chat.title;
              li.dataset.chatId = chat.id;
              if (chat.id === currentChatId) {
                  li.classList.add('active');
              }
              li.addEventListener('click', () => {
                  loadChat(chat.id);
              });
              chatHistoryList.appendChild(li);
          });
      })
      .catch(error => console.error('Error loading chats:', error));
  }
  
  function loadChat(chatId) {
      currentChatId = chatId;
      messagesContainer.innerHTML = '';
      
      // Update active state in sidebar
      const chatItems = document.querySelectorAll('#chat-history li');
      chatItems.forEach(item => {
          item.classList.remove('active');
          if (item.dataset.chatId === chatId) {
              item.classList.add('active');
          }
      });
      
      fetch(`/api/chat/${chatId}`)
      .then(response => response.json())
      .then(data => {
          if (data.messages && data.messages.length > 0) {
              welcomeMessage.classList.add('hidden');
              data.messages.forEach(msg => {
                  appendMessage(msg.user, 'user');
                  appendMessage(msg.assistant, 'assistant');
              });
              scrollToBottom();} else {
                welcomeMessage.classList.remove('hidden');
            }
        })
        .catch(error => console.error('Error loading chat:', error));
    }
    
    function sendMessage() {
        const message = chatInput.value.trim();
        if (!message || !currentChatId) return;
        
        welcomeMessage.classList.add('hidden');
        appendMessage(message, 'user');
        chatInput.value = '';
        
        fetch('/api/send-message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chatId: currentChatId,
                message: message
            })
        })
        .then(response => response.json())
        .then(data => {
            appendMessage(data.response, 'assistant');
            updateFeedback(data);
            playAudio(data.audio);
            scrollToBottom();
        })
        .catch(error => console.error('Error sending message:', error));
    }
    
    function toggleRecording() {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    }
    
    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.addEventListener('dataavailable', event => {
                audioChunks.push(event.data);
            });
            
            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                sendAudioMessage(audioBlob);
                
                // Clean up the stream
                stream.getTracks().forEach(track => track.stop());
            });
            
            mediaRecorder.start();
            isRecording = true;
            
            // Visual feedback for recording
            document.querySelector('.mic-on').classList.add('recording');
            
        } catch (error) {
            console.error('Error accessing microphone:', error);
            alert('Unable to access your microphone. Please check your permissions.');
            micToggle.checked = false;
        }
    }
    
    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            document.querySelector('.mic-on').classList.remove('recording');
        }
    }
    
    function sendAudioMessage(audioBlob) {
        if (!currentChatId) return;
        
        welcomeMessage.classList.add('hidden');
        
        const formData = new FormData();
        formData.append('audio', audioBlob);
        formData.append('chatId', currentChatId);
        
        // Show a placeholder for the user's message
        const placeholder = appendMessage('Processing your audio...', 'user');
        
        fetch('/api/send-audio', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            // Replace placeholder with actual transcription
            placeholder.textContent = data.message;
            
            // Add assistant response
            appendMessage(data.response, 'assistant');
            updateFeedback(data);
            playAudio(data.audio);
            scrollToBottom();
        })
        .catch(error => {
            console.error('Error sending audio:', error);
            placeholder.textContent = 'Error processing audio. Please try again.';
        });
    }
    
    function appendMessage(text, sender) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}-message`;
        messageElement.textContent = text;
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
        return messageElement;
    }
    
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    function updateFeedback(data) {
        // Update feedback panel with response data
        improvementsContent.textContent = data.improvements || "No improvements suggested.";
        suggestionsContent.textContent = data.suggestions || "No suggestions provided.";
        
        // Update fluency metrics if available
        if (data.fluency) {
            speechRateEl.textContent = data.fluency.speech_rate;
            speakingTimeEl.textContent = data.fluency.speaking_time;
            pauseCountEl.textContent = data.fluency.pause_count;
            errorRateEl.textContent = data.fluency.error_rate;
        }
        
        // Show feedback panel
        feedbackPanel.classList.remove('hidden');
    }
    
    function playAudio(audioUrl) {
        if (audioUrl) {
            audioPlayer.src = audioUrl;
            audioPlayer.play().catch(e => console.error('Error playing audio:', e));
        }
    }
});
