from flask import Flask, render_template, request, jsonify, send_from_directory, make_response, Response
import threading
import time
import random
import websocket
import os
import json
import requests
from datetime import datetime
import logging
import subprocess
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Включаем CORS для всех маршрутов
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
bots = []
stream_url = ""
is_auto_chat_active = False
auto_chat_thread = None
chat_messages = []
stream_process = None
stats = {
    "messages_sent": 0,
    "active_bots": 0,
    "viewer_count": 0
}

# Стили для веб-интерфейса
STYLES = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');
    
    :root {
        --primary-color: #9147ff;
        --secondary-color: #772ce8;
        --background-color: #0e0e10;
        --text-color: #ffffff;
        --border-color: #2a2a2d;
        --hover-color: #a970ff;
    }
    
    body {
        font-family: 'Montserrat', sans-serif;
        background-color: var(--background-color);
        color: var(--text-color);
        margin: 0;
        padding: 10px;
        height: 100vh;
        overflow: hidden;
    }
    
    .container {
        display: grid;
        grid-template-columns: 2fr 1fr;
        grid-template-rows: auto 1fr;
        gap: 10px;
        height: calc(100vh - 20px);
    }
    
    .stream-section {
        grid-row: 1 / 3;
        background-color: #1a1a1d;
        border-radius: 8px;
        padding: 10px;
        display: flex;
        flex-direction: column;
    }
    
    .stream-container {
        flex: 1;
        min-height: 0;
    }
    
    .stream-container iframe {
        width: 100%;
        height: 100%;
        border: none;
        border-radius: 4px;
    }
    
    .chat-section {
        background-color: #1a1a1d;
        border-radius: 8px;
        padding: 10px;
        display: flex;
        flex-direction: column;
    }
    
    .chat-messages {
        flex: 1;
        overflow-y: auto;
        margin-bottom: 10px;
    }
    
    .chat-message {
        margin-bottom: 8px;
        padding: 6px;
        border-radius: 4px;
        background-color: #2a2a2d;
        font-size: 14px;
    }
    
    .chat-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 2px;
    }
    
    .chat-username {
        color: var(--primary-color);
        font-weight: 600;
    }
    
    .chat-timestamp {
        color: #a0a0a0;
        font-size: 12px;
    }
    
    .chat-content {
        word-break: break-word;
    }
    
    .controls-section {
        background-color: #1a1a1d;
        border-radius: 8px;
        padding: 10px;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    
    .controls-group {
        display: flex;
        gap: 10px;
        align-items: center;
    }
    
    .bot-list {
        max-height: 150px;
        overflow-y: auto;
        background-color: #2a2a2d;
        border-radius: 4px;
        padding: 5px;
    }
    
    .bot-item {
        padding: 6px;
        margin: 2px 0;
        cursor: pointer;
        border-radius: 4px;
        font-size: 14px;
        transition: background-color 0.2s;
    }
    
    .bot-item:hover {
        background-color: var(--hover-color);
    }
    
    .bot-item.selected {
        background-color: var(--primary-color);
    }
    
    .stats-section {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
    }
    
    .stat-card {
        background-color: #2a2a2d;
        border-radius: 4px;
        padding: 8px;
        text-align: center;
    }
    
    .stat-value {
        font-size: 18px;
        font-weight: 700;
        color: var(--primary-color);
    }
    
    .stat-label {
        font-size: 12px;
        color: #a0a0a0;
    }
    
    button {
        background-color: var(--primary-color);
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 600;
        font-size: 14px;
        transition: background-color 0.2s;
        white-space: nowrap;
    }
    
    button:hover {
        background-color: var(--hover-color);
    }
    
    input[type="text"] {
        background-color: #2a2a2d;
        border: 1px solid var(--border-color);
        color: var(--text-color);
        padding: 8px;
        border-radius: 4px;
        font-size: 14px;
    }
    
    .file-upload {
        position: relative;
        overflow: hidden;
        display: inline-block;
    }
    
    .file-upload input[type="file"] {
        position: absolute;
        left: 0;
        top: 0;
        opacity: 0;
        cursor: pointer;
    }
    
    .file-upload-label {
        display: inline-block;
        padding: 8px 16px;
        background-color: var(--primary-color);
        color: white;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
    }
    
    .status-indicator {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 5px;
    }
    
    .status-active {
        background-color: #00ff00;
    }
    
    .status-inactive {
        background-color: #ff0000;
    }
</style>
"""

# HTML шаблон
HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Twitch Promoter</title>
    {STYLES}
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' http: https: ws: wss:; media-src *;">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
</head>
<body>
    <div class="container">
        <div class="stream-section">
            <h2>Twitch Stream</h2>
            <div class="stream-container">
                <video
                    id="stream-player"
                    controls
                    autoplay
                    width="100%"
                    height="100%">
                </video>
            </div>
        </div>
        
        <div class="chat-section">
            <h2>Twitch Chat</h2>
            <div class="chat-container">
                <iframe
                    src=""
                    frameborder="0"
                    scrolling="yes"
                    width="100%"
                    height="100%"
                    sandbox="allow-same-origin allow-scripts allow-popups allow-forms">
                </iframe>
            </div>
        </div>
        
        <div class="controls-section">
            <div class="controls-group">
                <input type="text" id="streamer-name" placeholder="Streamer name">
                <button onclick="loadStream()">Load Stream</button>
            </div>
            
            <div class="controls-group">
                <label class="file-upload-label">
                    Upload Bots
                    <input type="file" id="bots-file" accept=".txt">
                </label>
            </div>
            
            <div>
                <h3>Bots List</h3>
                <div class="bot-list" id="bots-list"></div>
            </div>
            
            <div class="controls-group">
                <input type="text" id="message" placeholder="Message">
                <button onclick="sendMessage()">Send</button>
            </div>
            
            <div class="controls-group">
                <button id="auto-chat-btn" onclick="toggleAutoChat()">Start Auto Chat</button>
            </div>
            
            <div class="stats-section">
                <div class="stat-card">
                    <div class="stat-value" id="messages-sent">0</div>
                    <div class="stat-label">Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="active-bots">0</div>
                    <div class="stat-label">Bots</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="viewer-count">0</div>
                    <div class="stat-label">Viewers</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let selectedBots = [];
        let hls = null;
        
        function loadStream() {{
            const streamerName = document.getElementById('streamer-name').value;
            if (streamerName) {{
                fetch('/load_stream', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{ streamer_name: streamerName }}),
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        const videoPlayer = document.getElementById('stream-player');
                        
                        if (hls) {{
                            hls.destroy();
                        }}
                        
                        hls = new Hls({{
                            debug: false,
                            enableWorker: true,
                            lowLatencyMode: true,
                            backBufferLength: 90
                        }});
                        
                        hls.loadSource(data.stream_url);
                        hls.attachMedia(videoPlayer);
                        hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                            videoPlayer.play();
                        }});
                        
                        const chatFrame = document.querySelector('.chat-container iframe');
                        chatFrame.src = data.chat_url;
                        
                        startChatConnection(streamerName);
                    }} else {{
                        alert('Error loading stream: ' + data.error);
                    }}
                }});
            }}
        }}
        
        function startChatConnection(streamerName) {{
            setInterval(() => {{
                fetch('/get_chat_messages')
                .then(response => response.json())
                .then(data => {{
                    updateChat(data.messages);
                }});
            }}, 5000);
        }}
        
        function updateChat(messages) {{
            const chatContainer = document.getElementById('chat-messages');
            chatContainer.innerHTML = '';
            messages.forEach(msg => {{
                const messageDiv = document.createElement('div');
                messageDiv.className = 'chat-message';
                messageDiv.innerHTML = `
                    <div class="chat-header">
                        <span class="chat-username">${{msg.username}}</span>
                        <span class="chat-timestamp">${{msg.timestamp}}</span>
                    </div>
                    <div class="chat-content">${{msg.message}}</div>
                `;
                chatContainer.appendChild(messageDiv);
            }});
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }}
        
        function toggleAutoChat() {{
            const button = document.getElementById('auto-chat-btn');
            const isActive = button.textContent.includes('Stop');
            
            fetch('/toggle_auto_chat', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{ active: !isActive }}),
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    button.textContent = isActive ? 'Start Auto Chat' : 'Stop Auto Chat';
                }}
            }});
        }}
        
        function sendMessage() {{
            const message = document.getElementById('message').value;
            if (message && selectedBots.length > 0) {{
                fetch('/send_message', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        message: message,
                        bot_indices: selectedBots
                    }}),
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        document.getElementById('message').value = '';
                    }} else {{
                        alert('Error sending message: ' + data.error);
                    }}
                }});
            }}
        }}
        
        function updateBotsList(bots) {{
            const botsList = document.getElementById('bots-list');
            botsList.innerHTML = '';
            
            bots.forEach((bot, index) => {{
                const botItem = document.createElement('div');
                botItem.className = 'bot-item';
                botItem.innerHTML = `
                    <span class="status-indicator ${{bot.active ? 'status-active' : 'status-inactive'}}"></span>
                    ${{bot.username}}
                `;
                botItem.onclick = () => toggleBotSelection(index, botItem);
                botsList.appendChild(botItem);
            }});
        }}
        
        function toggleBotSelection(index, element) {{
            const isSelected = element.classList.contains('selected');
            if (isSelected) {{
                element.classList.remove('selected');
                selectedBots = selectedBots.filter(i => i !== index);
            }} else {{
                element.classList.add('selected');
                selectedBots.push(index);
            }}
        }}
        
        document.getElementById('bots-file').addEventListener('change', function(e) {{
            const file = e.target.files[0];
            if (file) {{
                const formData = new FormData();
                formData.append('file', file);
                
                fetch('/upload_bots', {{
                    method: 'POST',
                    body: formData
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        updateBotsList(data.bots);
                    }} else {{
                        alert('Error uploading bots: ' + data.error);
                    }}
                }});
            }}
        }});
        
        setInterval(() => {{
            fetch('/get_stats')
            .then(response => response.json())
            .then(data => {{
                document.getElementById('messages-sent').textContent = data.messages_sent;
                document.getElementById('active-bots').textContent = data.active_bots;
                document.getElementById('viewer-count').textContent = data.viewer_count;
            }});
        }}, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # Очищаем предыдущий процесс при загрузке страницы
    global stream_process
    if stream_process:
        try:
            stream_process.terminate()
            stream_process.wait(timeout=5)
        except:
            stream_process.kill()
        stream_process = None
    return HTML_TEMPLATE

@app.route('/upload_bots', methods=['POST'])
def upload_bots():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file and file.filename.endswith('.txt'):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'bots.txt')
        file.save(file_path)
        
        # Чтение и обработка файла с ботами
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        global bots
        bots = []
        for line in lines:
            if ':' in line:
                username, password = line.strip().split(':', 1)
                bots.append({
                    'username': username,
                    'password': password,
                    'active': False,
                    'ws': None
                })
        
        return jsonify({
            'success': True,
            'bots': [{'username': bot['username'], 'active': bot['active']} for bot in bots]
        })
    
    return jsonify({'success': False, 'error': 'Invalid file format'})

@app.route('/load_stream', methods=['POST'])
def load_stream():
    data = request.get_json()
    streamer_name = data.get('streamer_name')
    
    if not streamer_name:
        return jsonify({'success': False, 'error': 'No streamer name provided'})
    
    try:
        # Останавливаем предыдущий процесс, если он существует
        global stream_process
        if stream_process:
            try:
                stream_process.terminate()
                stream_process.wait(timeout=5)
            except:
                stream_process.kill()
            stream_process = None
        
        # Проверяем, что стример онлайн
        check_url = f'https://www.twitch.tv/{streamer_name}'
        response = requests.get(check_url)
        if response.status_code != 200:
            return jsonify({'success': False, 'error': 'Streamer is offline or does not exist'})
        
        # Запускаем Streamlink в режиме HLS
        cmd = [
            'streamlink',
            '--player-external-http',
            '--player-external-http-port', '8080',
            '--player-external-http-header', 'Access-Control-Allow-Origin: *',
            '--player-external-http-header', 'Access-Control-Allow-Methods: GET, POST, OPTIONS',
            '--player-external-http-header', 'Access-Control-Allow-Headers: Content-Type',
            '--stream-segment-threads', '4',
            '--stream-segment-timeout', '30',
            '--stream-timeout', '30',
            '--stream-segment-attempts', '10',
            '--stream-segment-time', '2',
            '--hls-live-restart',
            '--hls-segment-threads', '4',
            f'twitch.tv/{streamer_name}',
            'best'
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stream_process = process
        
        # Ждем, пока Streamlink запустит HTTP сервер
        max_attempts = 10
        for _ in range(max_attempts):
            try:
                # Проверяем, что сервер запустился
                check_stream = requests.get('http://localhost:8080/stream.m3u8', timeout=1)
                if check_stream.status_code == 200:
                    return jsonify({
                        'success': True,
                        'stream_url': 'http://localhost:8080/stream.m3u8',
                        'chat_url': f'https://www.twitch.tv/embed/{streamer_name}/chat?parent=localhost&darkpopout',
                        'viewer_count': 0
                    })
            except:
                pass
            time.sleep(1)
        
        # Если сервер не запустился, возвращаем ошибку
        process.terminate()
        return jsonify({'success': False, 'error': 'Failed to start stream server'})
        
    except Exception as e:
        logger.error(f"Error loading stream: {str(e)}")
        if stream_process:
            try:
                stream_process.terminate()
            except:
                pass
            stream_process = None
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stream/<streamer_name>')
def stream(streamer_name):
    stream_file = os.path.join(app.config['UPLOAD_FOLDER'], f'{streamer_name}.m3u8')
    if os.path.exists(stream_file):
        return send_from_directory(app.config['UPLOAD_FOLDER'], f'{streamer_name}.m3u8')
    return '', 404

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    message = data.get('message')
    bot_indices = data.get('bot_indices', [])
    
    if not message or not bot_indices:
        return jsonify({'success': False, 'error': 'No message or bots selected'})
    
    try:
        for index in bot_indices:
            if 0 <= index < len(bots):
                bot = bots[index]
                if bot['active'] and bot['ws']:
                    bot['ws'].send(f"PRIVMSG #{stream_url.split('=')[1].split('&')[0]} :{message}\r\n")
                    stats['messages_sent'] += 1
                    # Добавляем сообщение в историю чата
                    chat_messages.append({
                        'username': bot['username'],
                        'message': message,
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })
                    # Ограничиваем количество сообщений в истории
                    if len(chat_messages) > 100:
                        chat_messages.pop(0)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/toggle_auto_chat', methods=['POST'])
def toggle_auto_chat():
    data = request.get_json()
    active = data.get('active', False)
    
    global is_auto_chat_active, auto_chat_thread
    
    if active and not is_auto_chat_active:
        is_auto_chat_active = True
        auto_chat_thread = threading.Thread(target=auto_chat_loop)
        auto_chat_thread.start()
    elif not active and is_auto_chat_active:
        is_auto_chat_active = False
        if auto_chat_thread:
            auto_chat_thread.join()
    
    return jsonify({'success': True})

def auto_chat_loop():
    messages = [
        "Hello everyone!",
        "Great stream!",
        "Let's go!",
        "PogChamp",
        "Kappa",
        "MonkaS",
        "LUL",
        "HeyGuys",
        "Nice play!",
        "GG"
    ]
    
    while is_auto_chat_active:
        try:
            active_bots = [bot for bot in bots if bot['active'] and bot['ws']]
            if active_bots:
                message = random.choice(messages)
                for bot in active_bots:
                    bot['ws'].send(f"PRIVMSG #{stream_url.split('=')[1].split('&')[0]} :{message}\r\n")
                    stats['messages_sent'] += 1
                    # Добавляем сообщение в историю чата
                    chat_messages.append({
                        'username': bot['username'],
                        'message': message,
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })
                    # Ограничиваем количество сообщений в истории
                    if len(chat_messages) > 100:
                        chat_messages.pop(0)
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error in auto chat: {str(e)}")
            time.sleep(5)

@app.route('/get_stats')
def get_stats():
    stats['active_bots'] = sum(1 for bot in bots if bot['active'])
    return jsonify(stats)

@app.route('/get_chat_messages')
def get_chat_messages():
    return jsonify({'messages': chat_messages})

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

if __name__ == '__main__':
    app.run(debug=True) 