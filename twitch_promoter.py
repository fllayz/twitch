import sys
import os
import random
import json
import websocket
import threading
import time
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                            QTextEdit, QMessageBox, QSpinBox, QFrame, QGridLayout,
                            QListWidget, QListWidgetItem, QSplitter, QProgressBar,
                            QComboBox)
from PyQt6.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter
import requests

class AnimatedPlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_angle)
        self.timer.start(50)  # Update every 50ms
        self.setMinimumSize(640, 360)
        
    def update_angle(self):
        self.angle = (self.angle + 2) % 360
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#16213e"))
        
        # Draw animated circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4a4e8c"))
        
        center = self.rect().center()
        radius = min(self.width(), self.height()) * 0.3
        
        # Draw rotating circle
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle)
        rect = QRectF(-radius/2, -radius/2, radius, radius)
        painter.drawEllipse(rect)
        painter.restore()
        
        # Draw text
        painter.setPen(QColor("#e6e6e6"))
        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(font)
        text = "Введите ник стримера для просмотра"
        text_rect = painter.fontMetrics().boundingRect(text)
        
        # Convert coordinates to integers
        x = int(center.x() - text_rect.width()/2)
        y = int(center.y() + text_rect.height()/2)
        
        painter.drawText(x, y, text)

class TwitchBot:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.ws = None
        self.connected = False
        self.channel = None
        self.last_error = None
        
    def connect(self, channel):
        self.channel = channel
        self.ws = websocket.WebSocket()
        try:
            # Устанавливаем таймаут
            self.ws.settimeout(10)
            
            # Подключаемся к серверу
            self.ws.connect("wss://irc-ws.chat.twitch.tv:443")
            
            # Отправляем команды аутентификации
            self.ws.send(f"PASS {self.password}")  # Убрал oauth: так как оно уже есть в токене
            self.ws.send(f"NICK {self.username}")
            
            # Ждем ответа на аутентификацию
            while True:
                auth_response = self.ws.recv()
                print(f"Auth response: {auth_response}")  # Для отладки
                
                if "Welcome" in auth_response:
                    break
                elif "Login authentication failed" in auth_response:
                    self.last_error = "Ошибка аутентификации: Неверный OAuth токен"
                    return False
                elif "Login unsuccessful" in auth_response:
                    self.last_error = "Ошибка аутентификации: Неверное имя пользователя или токен"
                    return False
                elif "Error logging in" in auth_response:
                    self.last_error = f"Ошибка входа: {auth_response}"
                    return False
                    
            # Подключаемся к каналу
            self.ws.send(f"JOIN #{self.channel}")
            
            # Ждем подтверждения подключения к каналу
            while True:
                join_response = self.ws.recv()
                print(f"Join response: {join_response}")  # Для отладки
                
                if f":{self.username}!{self.username}@{self.username}.tmi.twitch.tv JOIN #{self.channel}" in join_response:
                    break
                elif "Error joining" in join_response:
                    self.last_error = f"Ошибка подключения к каналу: {join_response}"
                    return False
                    
            self.connected = True
            return True
            
        except websocket.WebSocketTimeoutException:
            self.last_error = "Таймаут подключения к серверу"
            return False
        except websocket.WebSocketConnectionClosedException:
            self.last_error = "Соединение закрыто сервером"
            return False
        except Exception as e:
            self.last_error = f"Ошибка подключения: {str(e)}"
            return False
            
    def send_message(self, message):
        if not self.connected or not self.ws:
            self.last_error = "Бот не подключен к чату"
            return False
        try:
            # Отправляем сообщение
            self.ws.send(f"PRIVMSG #{self.channel} :{message}")
            
            # Ждем подтверждения отправки
            while True:
                response = self.ws.recv()
                print(f"Message response: {response}")  # Для отладки
                
                if f":{self.username}!{self.username}@{self.username}.tmi.twitch.tv PRIVMSG #{self.channel} :{message}" in response:
                    return True
                elif "Error sending message" in response:
                    self.last_error = f"Ошибка отправки сообщения: {response}"
                    return False
                    
        except websocket.WebSocketTimeoutException:
            self.last_error = "Таймаут отправки сообщения"
            return False
        except websocket.WebSocketConnectionClosedException:
            self.last_error = "Соединение закрыто при отправке сообщения"
            return False
        except Exception as e:
            self.last_error = f"Ошибка отправки сообщения: {str(e)}"
            return False
            
    def disconnect(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                self.last_error = f"Ошибка отключения: {str(e)}"
        self.connected = False

class MessageWorker(QThread):
    message_sent = pyqtSignal(str, str)  # username, message
    error_occurred = pyqtSignal(str, str, str)  # username, error, details
    finished = pyqtSignal()  # Сигнал о завершении работы
    
    def __init__(self, bot, channel, message, delay):
        super().__init__()
        self.bot = bot
        self.channel = channel
        self.message = message
        self.delay = delay
        
    def run(self):
        try:
            if not self.bot.connected:
                if not self.bot.connect(self.channel):
                    self.error_occurred.emit(self.bot.username, "Ошибка подключения", self.bot.last_error)
                    self.finished.emit()
                    return
                    
            if self.bot.send_message(self.message):
                self.message_sent.emit(self.bot.username, self.message)
            else:
                self.error_occurred.emit(self.bot.username, "Ошибка отправки сообщения", self.bot.last_error)
                
            time.sleep(self.delay)
        except Exception as e:
            self.error_occurred.emit(self.bot.username, "Неизвестная ошибка", str(e))
        finally:
            self.finished.emit()

class TwitchPromoter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Продвижение Twitch")
        self.setMinimumSize(1200, 800)
        
        # Initialize variables
        self.bot_instances = []  # Список экземпляров ботов
        self.is_promoting = False
        self.is_auto_chatting = False
        self.messages_sent = 0
        self.stream_start_time = None
        self.viewer_count = 0
        self.active_bots = 0
        self.custom_messages = []
        self.workers = []  # Список активных воркеров
        
        # Auto chat settings
        self.emojis = ["😊", "👍", "❤️", "🔥", "🎮", "💯", "🌟", "🎯", "💪", "👏"]
        self.messages = [
            "Отличный стрим!",
            "Круто играешь!",
            "Подписываюсь!",
            "Лучший стример!",
            "Спасибо за контент!",
            "Продолжай в том же духе!",
            "Зашел поддержать!",
            "Какой классный контент!",
            "Смотрю с удовольствием!",
            "Ты лучший!"
        ]
        
        # Set modern style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: #4a4e8c;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #5a5e9c;
            }
            QPushButton:pressed {
                background-color: #3a3e7c;
            }
            QPushButton:disabled {
                background-color: #2a2a4a;
                color: #666;
            }
            QLineEdit {
                padding: 12px;
                border: 2px solid #4a4e8c;
                border-radius: 8px;
                background-color: #16213e;
                color: white;
                font-size: 14px;
                min-height: 20px;
            }
            QLineEdit:focus {
                border: 2px solid #6a6eac;
                background-color: #1a1a2e;
            }
            QLabel {
                color: #e6e6e6;
                font-size: 14px;
            }
            QTextEdit {
                background-color: #16213e;
                color: white;
                border: 2px solid #4a4e8c;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                selection-background-color: #4a4e8c;
            }
            QSpinBox {
                padding: 12px;
                border: 2px solid #4a4e8c;
                border-radius: 8px;
                background-color: #16213e;
                color: white;
                font-size: 14px;
                min-height: 20px;
            }
            QSpinBox:focus {
                border: 2px solid #6a6eac;
                background-color: #1a1a2e;
            }
            QFrame {
                background-color: #16213e;
                border-radius: 12px;
                padding: 15px;
            }
            QLabel#statValue {
                font-size: 20px;
                font-weight: bold;
                color: #6a6eac;
            }
            QLabel#statLabel {
                font-size: 14px;
                color: #e6e6e6;
            }
            QListWidget {
                background-color: #16213e;
                color: white;
                border: 2px solid #4a4e8c;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #4a4e8c;
            }
            QListWidget::item:selected {
                background-color: #4a4e8c;
            }
            QSplitter::handle {
                background-color: #4a4e8c;
            }
            QProgressBar {
                border: 2px solid #4a4e8c;
                border-radius: 8px;
                text-align: center;
                background-color: #16213e;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #6a6eac;
                border-radius: 6px;
            }
        """)
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Create top control panel
        control_frame = QFrame()
        control_frame.setObjectName("controlFrame")
        control_frame.setStyleSheet("""
            QFrame#controlFrame {
                background-color: #16213e;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        control_layout = QHBoxLayout(control_frame)
        
        # Stream input
        self.stream_input = QLineEdit()
        self.stream_input.setPlaceholderText("Введите ник стримера")
        self.stream_input.setMinimumWidth(200)
        control_layout.addWidget(self.stream_input)
        
        # Load stream button
        self.load_stream_btn = QPushButton("Загрузить стрим")
        self.load_stream_btn.clicked.connect(self.load_stream)
        control_layout.addWidget(self.load_stream_btn)
        
        # Auto chat toggle
        self.auto_chat_btn = QPushButton("Включить авточат")
        self.auto_chat_btn.setCheckable(True)
        self.auto_chat_btn.clicked.connect(self.toggle_auto_chat)
        control_layout.addWidget(self.auto_chat_btn)
        
        # Promotion toggle
        self.promotion_btn = QPushButton("Начать продвижение")
        self.promotion_btn.setCheckable(True)
        self.promotion_btn.clicked.connect(self.toggle_promotion)
        control_layout.addWidget(self.promotion_btn)
        
        # Delay input
        delay_layout = QHBoxLayout()
        delay_label = QLabel("Задержка (сек):")
        self.delay_input = QSpinBox()
        self.delay_input.setRange(1, 60)
        self.delay_input.setValue(5)
        delay_layout.addWidget(delay_label)
        delay_layout.addWidget(self.delay_input)
        control_layout.addLayout(delay_layout)
        
        # Add bot selection for custom messages
        bot_selection_layout = QHBoxLayout()
        self.bot_selection = QComboBox()
        self.bot_selection.setPlaceholderText("Выберите бота")
        self.bot_selection.setMinimumWidth(200)
        bot_selection_layout.addWidget(self.bot_selection)
        
        # Add custom message input
        custom_message_layout = QHBoxLayout()
        self.custom_message_input = QLineEdit()
        self.custom_message_input.setPlaceholderText("Введите сообщение для бота")
        self.custom_message_input.setMinimumWidth(200)
        custom_message_layout.addWidget(self.custom_message_input)
        
        self.send_custom_message_btn = QPushButton("Отправить сообщение")
        self.send_custom_message_btn.clicked.connect(self.send_custom_message)
        custom_message_layout.addWidget(self.send_custom_message_btn)
        
        # Combine layouts
        custom_message_container = QVBoxLayout()
        custom_message_container.addLayout(bot_selection_layout)
        custom_message_container.addLayout(custom_message_layout)
        
        control_layout.addLayout(custom_message_container)
        
        layout.addWidget(control_frame)
        
        # Create splitter for stream and controls
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Stream view
        self.stream_view = QWebEngineView()
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.PlaybackRequiresUserGesture, False)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.JavascriptEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.LocalStorageEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.WebGLEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.PluginsEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.FullScreenSupportEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.AllowRunningInsecureContent, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.AllowWindowActivationFromJavaScript, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.ScrollAnimatorEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.ScreenCaptureEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.WebRTCPublicInterfacesOnly, False)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.DnsPrefetchEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.PdfViewerEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.PluginsEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.JavascriptCanOpenWindows, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.JavascriptCanAccessClipboard, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.SpatialNavigationEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.LinksIncludedInFocusChain, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.LocalContentCanAccessFileUrls, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.XSSAuditingEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.SpatialNavigationEnabled, True)
        self.stream_view.settings().setAttribute(self.stream_view.settings().WebAttribute.HyperlinkAuditingEnabled, True)
        
        splitter.addWidget(self.stream_view)
        
        # Right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Statistics frame
        stats_frame = QFrame()
        stats_frame.setObjectName("statsFrame")
        stats_layout = QGridLayout(stats_frame)
        
        # Messages sent
        messages_label = QLabel("Отправлено сообщений:")
        messages_label.setObjectName("statLabel")
        self.messages_value = QLabel("0")
        self.messages_value.setObjectName("statValue")
        stats_layout.addWidget(messages_label, 0, 0)
        stats_layout.addWidget(self.messages_value, 0, 1)
        
        # Active bots
        bots_label = QLabel("Активных ботов:")
        bots_label.setObjectName("statLabel")
        self.bots_value = QLabel("0")
        self.bots_value.setObjectName("statValue")
        stats_layout.addWidget(bots_label, 1, 0)
        stats_layout.addWidget(self.bots_value, 1, 1)
        
        # Viewer count
        viewers_label = QLabel("Зрителей:")
        viewers_label.setObjectName("statLabel")
        self.viewers_value = QLabel("0")
        self.viewers_value.setObjectName("statValue")
        stats_layout.addWidget(viewers_label, 2, 0)
        stats_layout.addWidget(self.viewers_value, 2, 1)
        
        right_layout.addWidget(stats_frame)
        
        # Bot list
        bot_list_label = QLabel("Боты:")
        self.bot_list = QListWidget()
        right_layout.addWidget(bot_list_label)
        right_layout.addWidget(self.bot_list)
        
        # Load bots button
        self.load_bots_btn = QPushButton("Загрузить ботов")
        self.load_bots_btn.clicked.connect(self.load_bots)
        right_layout.addWidget(self.load_bots_btn)
        
        # Log
        log_label = QLabel("Лог:")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(log_label)
        right_layout.addWidget(self.log_text)
        
        splitter.addWidget(right_panel)
        layout.addWidget(splitter)
        
        # Set initial sizes
        splitter.setSizes([800, 400])
        
        # Load bots on startup
        self.load_bots()
        
    def load_stream(self):
        channel = self.stream_input.text().strip()
        if not channel:
            QMessageBox.warning(self, "Предупреждение", "Введите ник стримера")
            return
            
        try:
            # Create stream URL with proper parameters
            url = f"https://player.twitch.tv/?channel={channel}&parent=localhost&muted=true"
            
            # Set URL and replace placeholder
            self.stream_view.setUrl(QUrl(url))
            layout = self.centralWidget().layout()
            splitter = layout.itemAt(1).widget()
            splitter.replaceWidget(0, self.stream_view)
            
            self.log_text.append(f"Загружен стрим: {channel}")
            self.stream_start_time = datetime.now()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить стрим: {str(e)}")
            
    def load_bots(self):
        try:
            if not os.path.exists('bots.txt'):
                QMessageBox.warning(self, "Предупреждение", 
                                  "Файл bots.txt не найден. Создан пустой файл.\n"
                                  "Добавьте ботов в формате: username:oauth:token\n"
                                  "Получите OAuth токен на https://twitchapps.com/tmi/")
                with open('bots.txt', 'w') as f:
                    f.write("# Добавьте ботов в формате: username:oauth:token\n")
                    f.write("# Получите OAuth токен на https://twitchapps.com/tmi/\n")
                return
            
            # Очищаем предыдущие списки
            self.bot_instances = []
            self.bot_list.clear()
            self.bot_selection.clear()
            
            with open('bots.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(':', 2)
                        if len(parts) == 3 and parts[1] == 'oauth':
                            username = parts[0]
                            oauth_token = f"{parts[1]}:{parts[2]}"
                            bot = TwitchBot(username, oauth_token)
                            self.bot_instances.append(bot)
                            self.bot_list.addItem(username)
                            self.bot_selection.addItem(username)
            
            self.active_bots = len(self.bot_instances)
            self.bots_value.setText(str(self.active_bots))
            self.log_text.append(f"Загружено ботов: {self.active_bots}")
            
            if self.active_bots == 0:
                QMessageBox.warning(self, "Предупреждение", 
                                  "Не удалось загрузить ни одного бота.\n"
                                  "Проверьте формат файла bots.txt\n"
                                  "Формат: username:oauth:token\n"
                                  "Получите OAuth токен на https://twitchapps.com/tmi/")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить ботов: {str(e)}")
            self.bot_instances = []

    def toggle_auto_chat(self):
        self.is_auto_chatting = not self.is_auto_chatting
        if self.is_auto_chatting:
            self.auto_chat_btn.setText("Выключить авточат")
            # Запускаем авточат в отдельном потоке
            auto_chat_thread = threading.Thread(target=self.run_auto_chat)
            auto_chat_thread.daemon = True
            auto_chat_thread.start()
        else:
            self.auto_chat_btn.setText("Включить авточат")
            
    def run_auto_chat(self):
        if not self.is_auto_chatting:
            return
            
        channel = self.stream_input.text().strip()
        if not channel:
            self.is_auto_chatting = False
            self.auto_chat_btn.setChecked(False)
            self.auto_chat_btn.setText("Включить авточат")
            return
            
        for bot in self.bot_instances:
            if not self.is_auto_chatting:
                break
                
            if not bot.connected:
                if not bot.connect(channel):
                    self.log_text.append(f"Ошибка подключения бота {bot.username}")
                    continue
                    
            try:
                message = random.choice(self.messages)
                emoji = random.choice(self.emojis)
                full_message = f"{message} {emoji}"
                
                if bot.send_message(full_message):
                    self.messages_sent += 1
                    # Обновляем UI в главном потоке
                    self.messages_value.setText(str(self.messages_sent))
                    self.log_text.append(f"Бот {bot.username} отправил: {full_message}")
                else:
                    self.log_text.append(f"Ошибка отправки сообщения от {bot.username}")
                
                time.sleep(self.delay_input.value())
            except Exception as e:
                self.log_text.append(f"Ошибка с ботом {bot.username}: {str(e)}")
                time.sleep(5)
                
        if self.is_auto_chatting:
            QTimer.singleShot(1000, self.run_auto_chat)
            
    def toggle_promotion(self):
        self.is_promoting = not self.is_promoting
        if self.is_promoting:
            self.promotion_btn.setText("Остановить продвижение")
            # Запускаем продвижение в отдельном потоке
            promotion_thread = threading.Thread(target=self.run_promotion, args=(self.stream_input.text().strip(),))
            promotion_thread.daemon = True
            promotion_thread.start()
        else:
            self.promotion_btn.setText("Начать продвижение")
            
    def run_promotion(self, channel):
        while self.is_promoting:
            for bot in self.bot_instances:
                if not self.is_promoting:
                    break
                    
                worker = MessageWorker(bot, channel, 
                                     f"{random.choice(self.messages)} {random.choice(self.emojis)}",
                                     self.delay_input.value())
                worker.message_sent.connect(self.handle_message_sent)
                worker.error_occurred.connect(self.handle_error)
                worker.finished.connect(self.check_all_workers_finished)
                self.workers.append(worker)
                worker.start()
                
                # Ждем завершения потока перед следующим ботом
                worker.wait()
                
    def update_statistics(self):
        # Обновляем статистику в главном потоке
        QTimer.singleShot(0, lambda: self.messages_value.setText(str(self.messages_sent)))
        QTimer.singleShot(0, lambda: self.bots_value.setText(str(self.active_bots)))
        QTimer.singleShot(0, lambda: self.viewers_value.setText(str(self.viewer_count)))

    def send_custom_message(self):
        message = self.custom_message_input.text().strip()
        if not message:
            QMessageBox.warning(self, "Предупреждение", "Введите сообщение")
            return
            
        selected_bot_username = self.bot_selection.currentText()
        if not selected_bot_username:
            QMessageBox.warning(self, "Предупреждение", "Выберите бота")
            return
            
        channel = self.stream_input.text().strip()
        if not channel:
            QMessageBox.warning(self, "Предупреждение", "Введите ник стримера")
            return
            
        # Находим выбранного бота
        selected_bot = None
        for bot in self.bot_instances:
            if bot.username == selected_bot_username:
                selected_bot = bot
                break
                
        if not selected_bot:
            QMessageBox.warning(self, "Предупреждение", "Выбранный бот не найден")
            return
            
        # Отключаем кнопку во время отправки
        self.send_custom_message_btn.setEnabled(False)
        
        # Создаем и запускаем поток для выбранного бота
        worker = MessageWorker(selected_bot, channel, message, self.delay_input.value())
        worker.message_sent.connect(self.handle_message_sent)
        worker.error_occurred.connect(self.handle_error)
        worker.finished.connect(self.check_all_workers_finished)
        self.workers = [worker]  # Используем только один воркер
        worker.start()
        
        self.custom_message_input.clear()
        
    def handle_message_sent(self, username, message):
        self.messages_sent += 1
        self.messages_value.setText(str(self.messages_sent))
        self.log_text.append(f"Бот {username} отправил: {message}")
        
    def handle_error(self, username, error_type, error_details):
        error_message = f"Ошибка с ботом {username}:\nТип: {error_type}\nДетали: {error_details}"
        self.log_text.append(error_message)
        print(f"Error: {error_message}")  # Для отладки
        
        # Если это ошибка аутентификации, показываем специальное сообщение
        if "аутентификации" in error_details:
            QMessageBox.warning(self, "Ошибка аутентификации", 
                              f"Ошибка аутентификации для бота {username}.\n"
                              f"Получите новый OAuth токен на https://twitchapps.com/tmi/\n"
                              f"и обновите его в файле bots.txt")
        
        # Если это критическая ошибка, отключаем бота
        if "подключения" in error_type.lower() or "соединение закрыто" in error_type.lower():
            for bot in self.bot_instances:
                if bot.username == username:
                    bot.disconnect()
                    self.log_text.append(f"Бот {username} отключен из-за ошибки")
                    break
                    
    def check_all_workers_finished(self):
        # Проверяем, все ли потоки завершились
        if all(not worker.isRunning() for worker in self.workers):
            self.send_custom_message_btn.setEnabled(True)
            self.workers = []  # Очищаем список воркеров
            
    def closeEvent(self, event):
        # Останавливаем все потоки перед закрытием
        for worker in self.workers:
            worker.quit()
            worker.wait()
            
        # Отключаем всех ботов
        for bot in self.bot_instances:
            try:
                bot.disconnect()
                if bot.last_error:
                    self.log_text.append(f"Ошибка при отключении бота {bot.username}: {bot.last_error}")
            except Exception as e:
                self.log_text.append(f"Критическая ошибка при отключении бота {bot.username}: {str(e)}")
                
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TwitchPromoter()
    window.show()
    sys.exit(app.exec()) 